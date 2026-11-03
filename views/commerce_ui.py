"""Commercial conditions and traceability on the existing document detail pages."""
import streamlit as st
from services import commerce,quotations as q
from views.common import managed_dialog,perform,table

def fields(data,prefix):
    d=dict(data)
    a,b=st.columns(2)
    d['production_authorized']=a.checkbox('Producción autorizada',value=d['production_authorized'],key=prefix+'_authorized')
    d['delivery_paid']=b.checkbox('Requerir saldo liquidado para entregar',value=d['delivery_paid'],key=prefix+'_paid')
    a,b=st.columns(2)
    modes=('Sin mínimo','Porcentaje','Importe')
    d['minimum_mode']=a.selectbox('Condición de anticipo',modes,index=modes.index(d['minimum_mode']),key=prefix+'_minimum')
    d['minimum_value']=b.number_input('Anticipo · %' if d['minimum_mode']=='Porcentaje' else 'Anticipo · MXN',min_value=0.0,
        value=float(d['minimum_value']),max_value=100.0 if d['minimum_mode']=='Porcentaje' else None,key=prefix+'_amount') if d['minimum_mode']!='Sin mínimo' else 0.0
    a,b=st.columns(2)
    d['source']=a.text_input('Origen del contacto',value=d['source'],placeholder='WhatsApp, Instagram, tienda…',key=prefix+'_source')
    segments=('Público','Mayoreo','Distribuidor','Otro')
    d['price_segment']=b.selectbox('Tipo de precio acordado',segments,index=segments.index(d['price_segment']) if d['price_segment'] in segments else 3,key=prefix+'_segment')
    a,b=st.columns(2)
    d['delivery_method']=a.selectbox('Entrega',('Por definir','Recolección','Entrega local','Paquetería'),index=('Por definir','Recolección','Entrega local','Paquetería').index(d['delivery_method']),key=prefix+'_delivery')
    from datetime import date
    due=b.date_input('Fecha prometida',value=date.fromisoformat(d['promised_on']) if d['promised_on'] else None,key=prefix+'_promise')
    d['promised_on']=due.isoformat() if due else ''
    d['delivery_reference']=st.text_input('Dirección, guía o referencia de entrega',value=d['delivery_reference'],key=prefix+'_reference')
    with st.expander('Responsables y capacidad de preparación'):
        for field,label in (('sales_owner','Responsable de venta'),('production_owner','Responsable de producción'),('delivery_owner','Responsable de entrega')):
            d[field]=st.text_input(label,value=d[field],key=prefix+'_'+field)
        a,b,c=st.columns(3)
        d['hours_per_day']=a.number_input('Horas de trabajo por día',min_value=0.0,max_value=24.0,value=d['hours_per_day'],key=prefix+'_hours')
        d['purchase_days']=b.number_input('Días para recibir insumos',min_value=0.0,max_value=365.0,value=d['purchase_days'],key=prefix+'_purchase')
        d['assembly_minutes']=c.number_input('Minutos de ensamble / lámpara',min_value=0.0,value=d['assembly_minutes'],key=prefix+'_assembly')
    d['agreement']=st.text_area('Acuerdos y condiciones particulares',value=d['agreement'],key=prefix+'_agreement')
    return d

@managed_dialog('Condiciones de venta y entrega',width='large')
def terms_form(kind,identity):
    token='commercial_profile_'+st.session_state['dialog_request_key']
    if token not in st.session_state:st.session_state[token]=commerce.profile(kind,identity)
    profile=st.session_state[token]
    st.caption('Condiciones editables de este documento. Los pagos se consultan del registro existente; los cambios quedan en el historial.')
    # Inputs are reactive so the amount field follows percentage or fixed amount immediately.
    payload=fields(profile['data'] if profile else commerce.defaults(),'commercial_terms_'+st.session_state['dialog_request_key'])
    reason=st.text_input('Motivo del cambio *',key='commercial_terms_reason')
    if st.button('Guardar condiciones',key='commercial_terms_save',type='primary'):
        perform(commerce.save,kind,identity,payload,expected_id=profile['id'] if profile else None,reason=reason,message='Condiciones comerciales guardadas.')

@managed_dialog('Cambio o cancelación',width='medium')
def request_form(kind,identity):
    with st.form('commercial_request'):
        category=st.selectbox('Tipo de solicitud',('Cambio','Cancelación'),key='commercial_request_kind')
        detail=st.text_area('Detalle / motivo *',key='commercial_request_detail')
        if st.form_submit_button('Registrar solicitud',type='primary'):
            perform(commerce.request,kind,identity,category,detail,message='Solicitud registrada en el historial.')

@managed_dialog('Resolver solicitud',width='medium')
def resolution_form(request):
    st.text(request['kind']+' · '+request['detail'])
    st.caption('Aplicar una cancelación requiere que no haya cobros vigentes ni producción iniciada. Las demás situaciones conservan la solicitud para documentar el acuerdo.')
    with st.form('commercial_resolution'):
        resolution=st.text_area('Resolución / acuerdo *',key='commercial_resolution_detail')
        apply=st.checkbox('Aplicar cancelación y liberar reservas sin avance',disabled=request['kind']!='Cancelación',key='commercial_resolution_apply')
        if st.form_submit_button('Guardar resolución',type='primary'):
            perform(commerce.resolve,request['id'],resolution,apply_cancel=apply,message='Resolución guardada.')

def panel(kind,identity):
    state=commerce.state(kind,identity);profile=state['profile'];d=profile['data'] if profile else commerce.defaults()
    with st.expander('Flujo comercial · producción y entrega',expanded=bool(profile),icon=':material/route:'):
        with st.container(horizontal=True):
            st.badge('Producción autorizada' if state['production_allowed'] else 'Revisar autorización',color='green' if state['production_allowed'] else 'orange')
            st.badge('Sin mínimo fijo' if d['minimum_mode']=='Sin mínimo' else 'Anticipo acordado · '+q.money(state['minimum_cents']),color='gray')
            if state['pending_cancellation']:st.badge('Cancelación pendiente',color='orange')
        st.caption(f"Cobrado {q.money(state['paid_cents'])} · Saldo {q.money(state['balance_cents'])} · Entrega: {d['delivery_method']} · Fecha prometida: {d['promised_on'] or 'Por definir'}")
        if not profile:st.caption('Documento anterior sin nuevas condiciones. Puedes incorporarlas de forma explícita.')
        if d['delivery_reference']:st.text(d['delivery_reference'])
        owners=[d[k] for k in ('sales_owner','production_owner','delivery_owner') if d[k]]
        if owners:st.caption('Responsables · '+' / '.join(owners))
        with st.container(horizontal=True):
            if st.button('Editar condiciones',key=f'commerce_terms_{kind}_{identity}',icon=':material/tune:'):terms_form(kind,identity)
            if st.button('Cambio o cancelación',key=f'commerce_request_{kind}_{identity}',icon=':material/history:'):request_form(kind,identity)
        history=commerce.history(kind,identity)
        for request in history['requests']:
            with st.container(horizontal=True,vertical_alignment='center'):
                st.text(request['kind']+' · '+request['state']+' · '+request['detail'])
                if request['state']=='Pendiente' and st.button('Resolver',key=f"commerce_resolve_{request['id']}"):resolution_form(request)
        with st.expander('Historial de condiciones y acuerdos'):
            table(history['events'],{'created_at':'Fecha','detail':'Movimiento comercial'},label='Historial de condiciones comerciales y solicitudes')
