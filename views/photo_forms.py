import streamlit as st
from services import photos
from views.common import managed_dialog,perform

@managed_dialog('Foto de producto o pieza',width='medium')
def photo_form(kind,identity,label,expected_revision=None):
    st.text(label)
    current=photos.get(kind,identity)
    if current: st.image(current['content'],width=320,alt=f'Foto actual de {label}')
    upload=st.file_uploader('Seleccionar fotografía',type=['jpg','jpeg','png','webp'],max_upload_size=10,
        key='photo_upload_'+st.session_state['dialog_request_key'])
    st.caption('La imagen se ajusta a 1600 px y se guarda en NIMUS, incluida en los respaldos. No cambia cantidades ni costos.')
    if upload:
        try:
            preview=photos.normalize(upload.getvalue())[0]
            st.image(preview,width=320,alt=f'Vista previa de {label}')
        except ValueError as exc:
            st.error(str(exc));return
        if st.button('Guardar foto',key='photo_save',type='primary',icon=':material/check:'):
            perform(photos.save,kind,identity,upload.getvalue(),expected_revision=expected_revision,message='Foto guardada.')
    if current:
        with st.popover('Quitar foto',icon=':material/delete:'):
            st.caption('Se quitará esta foto de la ficha. Puedes subir otra después.')
            if st.button('Confirmar quitar foto',key='photo_remove'):
                perform(photos.remove,kind,identity,expected_revision=expected_revision,message='Foto retirada.')

def photo_panel(kind,identity,label,*,key,fallback=None,width=280,gallery=False):
    own=photos.get(kind,identity)
    current=own or fallback
    if gallery:
        st.image(photos.thumbnail(current['content'] if current else None),width=width,alt=f'Fotografía de {label}' if current else f'{label} · Sin fotografía')
        st.caption('Foto propia' if own else 'Foto de catálogo' if current else 'Sin fotografía')
    elif current:
        st.image(current['content'],width=width,alt=f'Fotografía de {label}')
        if not own: st.caption('Foto compartida de la pieza del catálogo.')
    else: st.caption('Sin fotografía · Añade una imagen para reconocer esta referencia.')
    if st.button('Cambiar foto' if own else 'Agregar foto',key=key,icon=':material/add_photo_alternate:',type='tertiary'):
        photo_form(kind,identity,label,own['revision'] if own else None)
