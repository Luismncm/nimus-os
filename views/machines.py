import streamlit as st

from views.components import machine_card
from views.machine_forms import machine_form, remove_machine_form
from views.common import perform
from services.machines import archive_machine

snapshot = st.session_state["snapshot"]
machines = snapshot["machines"]
available = sum(m["status"] == "Disponible" for m in machines)
running = sum(m["status"] == "Imprimiendo" for m in machines)
from views.shell import actions
with actions():
    if st.button('Agregar máquina',key='machine_add',type='primary',icon=':material/add:'):
        machine_form()
with st.container(horizontal=True,gap='small'):
    st.badge(f"{available} disponibles",color='green' if available else 'gray',icon=':material/check_circle:')
    st.badge(f"{running} en producción",color='blue' if running else 'gray',icon=':material/autorenew:')
    attention=len(machines)-available-running
    st.badge(f"{attention} requieren atención",color='orange' if attention else 'gray',icon=':material/build:')
if not machines:
    st.info('Agrega una máquina para comenzar o reactiva una archivada.')
def manage(machine):
    """Editing and retiring sit inside the printer's own card, never loose under a neighbour's."""
    def draw():
        with st.container(horizontal=True,gap='small'):
            if st.button('Editar máquina',key=f'machine_edit_{machine["id"]}',icon=':material/edit:'):
                machine_form(machine)
            if st.button('Retirar',key=f'machine_remove_{machine["id"]}',type='tertiary',icon=':material/archive:'):
                remove_machine_form(machine,any(j['machine_id']==machine['id'] for j in snapshot['jobs']))
    return draw


for start in range(0,len(machines),3):
    for column,machine in zip(st.columns(3,gap='medium'),machines[start:start+3]):
        with column:
            machine_card(machine,manage(machine))
archived = [m for m in snapshot['all_machines'] if m['archived']]
if archived:
    with st.expander(f'Máquinas archivadas · {len(archived)}'):
        for machine in archived:
            st.write(f"**{machine['code']} · {machine['name']}**")
            if st.button('Reactivar',key=f'machine_restore_{machine["id"]}'):
                perform(archive_machine,machine['id'],False,message='Máquina reactivada.')
st.caption("Cada máquina admite un trabajo en producción. Inicia, pausa y termina sus impresiones en la cola (Operar en la cola); pausar o terminar libera la máquina.")
