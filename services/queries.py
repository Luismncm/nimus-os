"""Read a consistent snapshot in five queries; aggregate each part exactly once."""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime

from db import connect
from models.constants import PRIORITY_RANK
from utils.calculations import progress, totals
from services.order_progress import annotate as annotate_progress
from utils.dates import now, parse_deadline, parse_end
from utils.csv_export import csv_bytes as export


def piece_label(name: str, model: str) -> str:
    """Piece and its model, once: PANTALLA · CIRRUS; a name that already says its model stays as it is."""
    return f"{name} · {model}" if model and model.casefold() not in (name or '').casefold() else name


def job_sort(job: dict) -> tuple:
    return (PRIORITY_RANK[job["priority"]], job["deadline"] or "9999-12-31",
            job["expected_end"] or "9999-12-31", job["id"])


def load_snapshot(conn=None) -> dict:
    with (nullcontext(conn) if conn is not None else connect()) as conn:
        tables = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
                  for table in ("orders","items","parts","production_jobs","machines")}
        from services.planning import annotate as annotate_plans
        annotate_plans(conn,tables["production_jobs"])
        from services.quality import annotate as annotate_quality
        from services.consumption import annotate as annotate_consumption
        annotate_quality(conn,tables["production_jobs"])
        annotate_consumption(conn,tables["production_jobs"])
        from services.operations import annotate
        annotate(conn,tables["items"],tables["orders"])
        from services.recipes import load_requirements
        requirements = load_requirements(conn)
        recipe_versions = {r['id']: r['version'] for r in conn.execute('SELECT id,version FROM recipe_versions')}
        origin_recipes={r[0] for r in conn.execute('SELECT recipe_id FROM origin_recipes')}
        cancelled={r['order_id']:r['reason'] for r in conn.execute('SELECT * FROM order_cancellations')} if conn.execute("SELECT 1 FROM sqlite_master WHERE name='order_cancellations'").fetchone() else {}
        development={r['order_id']:dict(r) for r in conn.execute('SELECT * FROM development_projects')} if conn.execute("SELECT 1 FROM sqlite_master WHERE name='development_projects'").fetchone() else {}
        from services.stock_runs import runs as stock_runs, GENERAL
        stock=stock_runs(conn)
        loadout={r['machine_id']:r['material'] for r in conn.execute('SELECT * FROM machine_loadout')} if conn.execute("SELECT 1 FROM sqlite_master WHERE name='machine_loadout'").fetchone() else {}
        for machine in tables['machines']:machine['loaded_material']=loadout.get(machine['id'],'')
        from services.piece_stock import annotate as annotate_stock
        annotate_stock(conn,tables['parts'],tables['production_jobs'])
        models={r['id']:(r['variant'] or '').strip() for r in conn.execute('SELECT id,variant FROM catalog_components')} if conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalog_components'").fetchone() else {}
    orders = {row["id"]:row for row in tables["orders"]}
    items = {row["id"]:row for row in tables["items"]}
    parts = {row["id"]:row for row in tables["parts"]}
    machines = {row["id"]:row for row in tables["machines"]}
    for order in orders.values():
        order["items"] = []
        # Internal prototyping: printed and costed like any order, never a sale or a delivery.
        order['development'] = development.get(order['id'])
        # Prints straight to inventory: an internal order with no customer, closed when printed.
        order['stock_run'] = stock.get(order['id'])
        if order['id'] in cancelled:order.update(commercial_cancelled=True,cancellation_reason=cancelled[order['id']])
    for item in items.values():
        item['is_origin_lamp']=item['recipe_id'] in origin_recipes
        item.update(code=f"ITEM-{item['id']:04d}",parts=[])
        orders[item["order_id"]]["items"].append(item)
    for part in parts.values():
        item = items[part["item_id"]]
        order = orders[item["order_id"]]
        # A piece is shown by its model (PANTALLA · CIRRUS), never only by its material: the stored name is kept as base_name.
        # The model comes from its catalog piece, from the catalog piece a stock print was launched for, or from the model typed for it.
        run = stock.get(order['id']) or {}
        model = models.get(part.get('component_id') or run.get('component_id'), '')
        if not model and run and item['name'] != GENERAL and not item['name'].startswith('CMP-'):
            model = item['name']
        part.update(base_name=part['name'],model=model,name=piece_label(part['name'],model))
        part.update(code=f"PART-{part['id']:04d}",jobs=[],quantity_completed=0,quantity_assigned=0,
                    item_name=item["name"],item_code=item["code"],order_id=order["id"],order_code=order["code"],
                    project=order["project"],order_status=order["status"],order_priority=order["priority"],collection=item['collection'])
        item["parts"].append(part)
        if order.get('commercial_cancelled'):part['commercial_cancelled']=True
    for job in tables["production_jobs"]:
        part = parts[job["part_id"]]
        order = orders[part["order_id"]]
        machine = machines.get(job["machine_id"],{})
        job.update(part_name=part["name"],part_code=part["code"],process=part["process"],material=part["material"],
                   item_name=part["item_name"],item_code=part["item_code"],order_id=order["id"],order_code=order["code"],
                   project=order["project"],client=order["client"],deadline=order["deadline"],order_priority=order["priority"],
                   order_status=order["status"],order_blocked=order["blocked_manually"],machine_code=machine.get("code"),
                   quantity_remaining=job["quantity"]-job["quantity_completed"],collection=part['collection'],
                   development=bool(order['development']),stock_run=bool(order['stock_run']))
        part["jobs"].append(job)
        if order.get('commercial_cancelled'):job['commercial_cancelled']=True
        part["quantity_completed"] += job["quantity_completed"]
        part["quantity_assigned"] += job["quantity"]
    for part in parts.values():
        part.update(quantity_remaining=part["quantity_required"]-part["quantity_completed"],
                    quantity_unassigned=part["quantity_required"]-part["quantity_assigned"],
                    progress=progress(part["quantity_required"],part["quantity_completed"]))
    for item in items.values():
        item.update(totals(item["parts"]))
        item['requirements'] = [r for r in requirements if r['item_id'] == item['id']]
        item['recipe_version'] = recipe_versions.get(item['recipe_id'])
        if item['recipe_id']:
            required = sum(r['quantity'] for r in item['requirements'])
            covered = sum(r['covered'] for r in item['requirements'])
            item.update(required_total=required, completed_total=covered, remaining_total=required-covered, progress=progress(required, covered))
        annotate_progress(item)
    for order in orders.values():
        required = sum(i['required_total'] for i in order['items'])
        completed = sum(i['completed_total'] for i in order['items'])
        order.update(required_total=required, completed_total=completed, remaining_total=required-completed, progress=progress(required, completed))
        order["undefined_items"] = sum(not item["parts"] and not item['recipe_id'] for item in order["items"])
        annotate_progress(order)
    jobs = sorted(tables["production_jobs"],key=job_sort)
    for machine in machines.values():
        assigned = [j for j in jobs if j["machine_id"] == machine["id"] and j["order_status"] != "Entregado" and not j.get('commercial_cancelled')]
        machine["current_job"] = next((j for j in assigned if j["status"] == "En producción"),None)
        machine["next_job"] = next((j for j in sorted(assigned,key=lambda j:(j["planned_start"] or "9999-12-31",job_sort(j))) if j["status"] in ("En cola","Pausado") and not j["order_blocked"]),None)
        machine["pending_units"] = sum(j["quantity_remaining"] for j in assigned)
    result = {"orders":sorted(orders.values(),key=lambda o:(PRIORITY_RANK[o["priority"]],o["deadline"] or "9999-12-31",o["id"])),
            "items":list(items.values()),"parts":list(parts.values()),"jobs":jobs,
            "machines":sorted((m for m in machines.values() if not m['archived']),key=lambda m:m["code"]),
            "all_machines":sorted(machines.values(),key=lambda m:m["code"])}
    from services.planning import schedule
    board=schedule(result)
    late_ids={j['id'] for j in board['late']}
    for job in jobs:
        job['schedule_conflicts']=sorted(board['conflicts'].get(job['id'],set()))
        job['overdue_schedule']=job['id'] in late_ids
    return result



def filter_jobs(jobs: list[dict], *, machine: int | str = "Todas", status: str = "Todos",
                priority: str = "Todas", order_id: int | None = None, process: str = "Todos") -> list[dict]:
    return [j for j in jobs if (not j.get('commercial_cancelled') or order_id is not None) and
            (machine == "Todas" or j["machine_id"] == (None if machine == "Sin máquina" else machine)) and
            (status == "Todos" or j["status"] == status) and
            (priority == "Todas" or j["priority"] == priority) and
            (order_id is None or j["order_id"] == order_id) and
            (process == "Todos" or j["process"] == process)]


def dashboard(snapshot: dict, at: datetime | None = None) -> dict:
    at = at or now()
    today = at.date()
    active_orders = [o for o in snapshot["orders"] if o["status"] != "Entregado" and not o.get('commercial_cancelled')]
    jobs = [j for j in snapshot["jobs"] if j["status"] != "Terminado" and j["order_status"] != "Entregado" and j['order_id'] not in {o['id'] for o in snapshot['orders'] if o.get('commercial_cancelled')}]
    overdue, due_today, invalid_dates = [], [], []
    for job in jobs:
        try:
            end, deadline = parse_end(job["expected_end"]),parse_deadline(job["deadline"])
            if (end and end < at) or (not end and deadline and deadline < today):
                overdue.append(job)
            if (end and end.date() == today) or (not end and deadline == today):
                due_today.append(job)
        except ValueError:
            invalid_dates.append(job)
    machines = {m["id"]:m for m in snapshot["machines"]}
    candidates = [j for j in jobs if j["status"] in ("En cola","Pausado") and not j["order_blocked"] and
                  (j["machine_id"] is None or machines[j["machine_id"]]["status"] == "Disponible")]
    urgent = [o for o in active_orders if o["priority"] == "Alta" or (o["deadline"] and o["deadline"] <= today.isoformat()) or o["status"] == "Bloqueado"]
    busy = sum(m["current_job"] is not None for m in machines.values())
    return {"orders":active_orders,"urgent_orders":urgent,"overdue":overdue,"due_today":due_today,
            "blocked":[j for j in jobs if j["status"] == "Bloqueado"],
            "running":[j for j in jobs if j["status"] == "En producción"],
            "next_job":candidates[0] if candidates else None,"invalid_dates":invalid_dates,
            "metrics":{"active_orders":len(active_orders),"blocked_orders":sum(o["status"] == "Bloqueado" for o in active_orders),
                       "active_jobs":len(jobs),"overdue_jobs":len(overdue),
                       "pending_units":sum(o["manufacturing"]["remaining"] for o in active_orders),
                       "busy_machines":busy,"machine_count":len(machines),
                       "utilization":round(100*busy/len(machines)) if machines else 0}}


EXPORT_FIELDS = ("order_code","client","project","deadline","priority","order_status","item_code","item","item_quantity",
                 "part_code","part","quantity_required","part_quantity_completed","quantity_unassigned","process","material",
                 "job_code","job_quantity","completed_quantity","quantity_completed","job_status","job_priority","machine",
                 "started_at","expected_end","completed_at","order_notes","item_notes","part_notes","job_notes")


def export_rows(snapshot: dict) -> list[dict]:
    rows = []
    for order in snapshot["orders"]:
        for item in order["items"] or [{}]:
            for part in item.get("parts") or [{}]:
                for job in part.get("jobs") or [{}]:
                    rows.append(dict(zip(EXPORT_FIELDS, (
                        order["code"],order["client"],order["project"],order["deadline"],order["priority"],order["status"],
                        item.get("code"),item.get("name"),item.get("quantity"),part.get("code"),part.get("name"),
                        part.get("quantity_required"),part.get("quantity_completed"),part.get("quantity_unassigned"),part.get("process"),part.get("material"),
                        job.get("code"),job.get("quantity"),job.get("quantity_completed"),job.get("quantity_completed"),job.get("status"),job.get("priority"),
                        job.get("machine_code"),job.get("started_at"),job.get("expected_end"),job.get("completed_at"),
                        order["notes"],item.get("notes"),part.get("notes"),job.get("notes")))))
    return rows


def csv_bytes(rows: list[dict], fields: tuple[str,...] = EXPORT_FIELDS) -> bytes:
    return export(fields, ([row.get(f) for f in fields] for row in rows))


PART_EXPORT_FIELDS = ("code","order_code","project","order_status","item_code","item_name","name","process","material",
                      "quantity_required","quantity_assigned","quantity_completed","quantity_remaining","quantity_unassigned","progress")
