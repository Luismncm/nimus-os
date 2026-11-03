import streamlit as st
from services import invoices
from views.common import managed_dialog,perform


@managed_dialog('Factura y PDF',width='medium')
def invoice_form(kind,identity):
    row=invoices.get(kind,identity)
    prefix='invoice_'+st.session_state['dialog_request_key']
    st.write(f"**{row['code']}**")
    with st.form(prefix):
        required=st.radio('¿Lleva factura?',('Sí','No'),index=None if row['required'] is None else 0 if row['required'] else 1,key=prefix+'_required',horizontal=True)
        reference=st.text_input('Folio / referencia de factura',value=row['reference'],key=prefix+'_reference')
        upload=st.file_uploader('Adjuntar o reemplazar PDF · máximo 10 MB',type=['pdf'],max_upload_size=10,key=prefix+'_pdf')
        clear=st.checkbox('Retirar PDF adjunto',key=prefix+'_clear') if row['filename'] else False
        if row['filename']:st.caption('Archivo actual: '+row['filename'])
        st.caption('Puedes marcar Sí y agregar el PDF después. Esta selección no cambia el IVA, el total ni los pagos.')
        if st.form_submit_button('Guardar factura',type='primary',width='stretch'):
            if required is None:
                st.error('Indica si lleva factura o no.')
                return
            perform(invoices.save,kind,identity,required=='Sí',reference,(upload.name,upload.getvalue()) if upload else None,clear,
                expected_revision=row['revision'],expected_owner_revision=row['owner_revision'],message='Factura guardada.')


def invoice_panel(kind,identity):
    row=invoices.get(kind,identity)
    state='Por definir' if row['required'] is None else 'No lleva factura' if not row['required'] else 'Factura con PDF' if row['content'] else 'Factura · PDF pendiente'
    with st.container(border=True):
        a,b=st.columns([3,1],vertical_alignment='center')
        a.subheader('Factura y PDF', icon=':material/attach_file:')
        a.write(state)
        if b.button('Gestionar factura',key=f'invoice_manage_{kind}_{identity}',icon=':material/attach_file:',disabled=not row['editable'],width='stretch'):
            invoice_form(kind,identity)
        if row['reference']:st.caption('Folio / referencia: '+row['reference'])
        if row['content']:
            st.download_button('Descargar PDF de factura',row['content'],file_name=row['filename'],mime='application/pdf',key=f'invoice_download_{kind}_{identity}',icon=':material/picture_as_pdf:')
            st.caption(row['filename']+' · Guardado en la base local y sus respaldos.')
        elif row['required']:st.info('Falta adjuntar el PDF. Puedes agregarlo en Gestionar factura.')
