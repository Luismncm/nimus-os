"""Compact navigation counts; multiple alerts about one record count as one pending."""

def summarize(supplies,events,limit=2):
    active=sorted((r for r in supplies if r['attention']),key=lambda r:(-r['score'],r['net'],r['id']))
    grouped={}
    for event in sorted(events,key=lambda r:-r.get('score',0)):
        if event['record_kind']=='Insumo' or event['state']!='Pendiente':continue
        grouped.setdefault((event['record_kind'],event['record_id']),event)
    pending=list(grouped.values())
    return dict(supply_count=len(active),critical_count=sum(r['critical'] for r in active),pending_count=len(pending),
        total=len(active)+len(pending),supplies=active[:limit],pending=pending[:limit])
