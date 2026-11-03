import streamlit as st
from models.constants import MACHINE_STATUSES
from services import machines
from views.common import managed_dialog, perform


@managed_dialog('Máquina',width='medium')
def machine_form(machine=None):
    row = machine or {}
    with st.form('machine_details'):
        a,b = st.columns(2)
        code = a.text_input('Código *',value=row.get('code',''),key='machine_edit_code',placeholder='Ej. P5')
        name = b.text_input('Nombre *',value=row.get('name',''),key='machine_edit_name',placeholder='Ej. Bambu Lab A1')
        statuses = [row['status']] if row.get('current_job') else [s for s in MACHINE_STATUSES if s != 'Imprimiendo']
        state = st.selectbox('Disponibilidad',statuses,index=statuses.index(row.get('status','Disponible')),key='machine_edit_status')
        notes = st.text_area('Notas',value=row.get('notes',''),key='machine_edit_notes')
        if row.get('current_job'):
            st.caption('Pausa o termina el trabajo activo para cambiar la disponibilidad.')
        if st.form_submit_button('Guardar máquina',type='primary',width='stretch',key='machine_details_save'):
            perform(machines.save_machine,code,name,state,notes,machine_id=row.get('id'),message='Máquina guardada.')


@managed_dialog('Retirar máquina')
def remove_machine_form(machine, has_history):
    st.write(f"**{machine['code']} · {machine['name']}**")
    st.caption('Tiene historial: se archivará y podrás reactivarla después. Primero termina o reasigna los trabajos pendientes.' if has_history else
               'No tiene trabajos asociados. Se puede eliminar del catálogo de máquinas.')
    if st.button('Archivar máquina' if has_history else 'Eliminar máquina',type='primary',key='machine_remove_confirm'):
        perform(machines.archive_machine if has_history else machines.remove_machine,machine['id'],message='Máquina retirada de la lista activa.')
