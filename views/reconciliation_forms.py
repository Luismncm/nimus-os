from datetime import date
import json
import streamlit as st
from services import reconciliation as r,expenses,treasury
from views.common import managed_dialog,perform
from views.expense_forms import fields,expense_category,expense_subtype
from utils.dates import now


def correction_history(source,rid):
    entries=r.history(source,rid)
    with st.expander(f'Historial · {len(entries)} registros' if source=='capital' else f'Historial de conciliación · {len(entries)} cambios'):
        if not entries: st.caption('Todavía no hay correcciones registradas.')
        labels={'amount_cents':'Importe','total_cents':'Total','subtotal_cents':'Subtotal','tax_cents':'IVA',
            'paid_on':'Fecha del pago','expense_on':'Fecha del gasto','moved_on':'Fecha de aportación','account_id':'Cuenta efectiva',
            'account':'Cuenta prevista','concept':'Concepto','party':'Contraparte','partner':'Socio','reference':'Referencia',
            'category':'Categoría','supplier':'Proveedor','receipt':'Comprobante','receipt_type':'Comprobante','receipt_ref':'Folio',
            'method':'Método','notes':'Notas','due_on':'Vencimiento','tax_mode':'Desglose','unit':'Unidad','subtype':'Tipo de gasto','cost_type':'Naturaleza',
            'voided_at':'Anulado el','void_reason':'Motivo de anulación'}
        accounts={a['id']:a['name'] for a in treasury.accounts()}
        def value(key,v):
            if key.endswith('_cents') and v is not None: return expenses.money(v)
            if key=='account_id': return accounts.get(v,'Sin cuenta')
            return str(v) if v not in (None,'') else 'Sin dato'
        for entry in entries:
            st.write(f"**{entry['created_at']} · {entry['reason']}**")
            before,after=json.loads(entry['before_json']),json.loads(entry['after_json'])
            changes=[{'Dato':label,'Anterior':value(key,before.get(key)),'Corregido':value(key,after.get(key))}
                for key,label in labels.items() if before.get(key)!=after.get(key)]
            for collection,label in (('payments','Pago'),('partners','Pago del socio'),('capital','Movimiento de socio')):
                old={p.get('id',p.get('expense_id')):p for p in before.get(collection,[])}
                for p in after.get(collection,[]):
                    previous=old.get(p.get('id',p.get('expense_id')), {})
                    for key in ('amount_cents','paid_on','moved_on'):
                        if previous.get(key)!=p.get(key):
                            changes.append({'Dato':f'{label} · {labels[key]}','Anterior':value(key,previous.get(key)),'Corregido':value(key,p.get(key))})
            if changes: st.dataframe(changes,hide_index=True,width='stretch')


@managed_dialog('Conciliar movimiento',width='large')
def movement_form(source,rid,before):
    capital=source=='capital'
    prefix='reconcile_'+st.session_state['dialog_request_key']
    st.caption('Corrige la captura contra tu comprobante o estado de cuenta. Se conserva la versión anterior y se recalculan los saldos.')
    with st.form(prefix):
        a,b=st.columns(2)
        amount=a.number_input('Importe · MXN',min_value=.01,value=before['amount_cents']/100,step=1.,key=prefix+'_amount')
        old_day=before['moved_on'] if capital else before['paid_on']
        day=b.date_input('Fecha del movimiento',value=date.fromisoformat(old_day) if old_day else None,max_value=now().date(),key=prefix+'_date')
        accounts={a['id']:a for a in treasury.accounts() if a['active'] or a['id']==before['account_id']}
        options=[None,*accounts]
        aid=st.selectbox('Cuenta efectiva *',options,index=options.index(before['account_id']),
            format_func=lambda i:'Selecciona una cuenta' if i is None else accounts[i]['name']+(' · Archivada' if not accounts[i]['active'] else ''),key=prefix+'_account')
        data=dict(amount=amount,paid_on=day.isoformat() if day else '',account_id=aid)
        if capital:
            a,b=st.columns(2)
            data['partner']=a.text_input('Socio',value=before['partner'],key=prefix+'_partner')
            data['party']=b.text_input('Contraparte / titular',value=before['party'],key=prefix+'_party')
            data['concept']=st.text_input('Concepto *',value=before['concept'],key=prefix+'_concept')
            data['receipt']=st.text_input('Comprobante',value=before['receipt'],key=prefix+'_receipt')
            data['reference']=st.text_input('Referencia bancaria / folio',value=before['reference'],key=prefix+'_reference')
            data['notes']=st.text_area('Notas',value=before['notes'],key=prefix+'_notes')
        else:
            if source!='expense': data['concept']=st.text_input('Concepto *',value=before['concept'],key=prefix+'_concept')
            data['method']=st.text_input('Método *',value=before['method'],key=prefix+'_method')
            data['reference']=st.text_input('Referencia',value=before['reference'],key=prefix+'_reference')
        reason=st.text_input('Motivo de la corrección *',placeholder='Fecha e importe verificados contra el estado de cuenta',key=prefix+'_reason')
        if st.form_submit_button('Guardar conciliación',type='primary',width='stretch'):
            perform(r.correct_movement,source,rid,data,expected=r.token(before),reason=reason,message='Movimiento corregido. Saldos e historial actualizados.')
    correction_history(source,rid)


@managed_dialog('Conciliar gasto',width='large')
def expense_reconciliation_form(row,before):
    prefix='reconcile_expense_'+st.session_state['dialog_request_key']
    st.write(f"**{row['code']} · {row['concept']}**")
    st.caption('Puedes corregir importes, IVA y datos del gasto. La cuenta prevista del gasto y la cuenta efectiva de cada pago son independientes.')
    active=[p for p in before['payments'] if not p['voided_at']]
    full=len(active)==1 and active[0]['amount_cents']==before['total_cents'] and not before['partners']
    editable=expenses.editable(row)
    category=expense_category(st,editable,prefix)
    subtype=expense_subtype(editable,category,prefix)
    with st.form(prefix):
        data=fields(editable,prefix,labels=(category,subtype))
        sync=False;partner_day=None
        if full:
            sync=st.checkbox('Ajustar también el importe del pago completo',value=False,key=prefix+'_sync')
        elif active: st.caption('Los abonos se corrigen individualmente desde Pagos o Tesorería → Movimientos. El total no puede quedar por debajo de lo pagado.')
        if before['partners']:
            previous=before['partners'][0]['paid_on']
            day=st.date_input('Fecha de compra pagada por el socio',value=date.fromisoformat(previous) if previous else None,max_value=now().date(),key=prefix+'_partnerdate')
            partner_day=day.isoformat() if day else ''
            st.caption('El importe cubierto por el socio se ajustará al total corregido. Esta compra no genera salida de banco ni caja.')
        reason=st.text_input('Motivo de la corrección *',key=prefix+'_reason')
        if st.form_submit_button('Guardar conciliación del gasto',type='primary',width='stretch'):
            perform(r.correct_expense,row['id'],data,expected=r.token(before),reason=reason,sync_payment=sync,
                partner_day=partner_day,message='Gasto conciliado. Importes e historial actualizados.')
    correction_history('expense_document',row['id'])
