import streamlit as st
from textwrap import shorten
from services import costing,recipes
from services.quotations import cents,money
from views.common import managed_dialog,perform,table
from views.emoji import tag


def amount_field(container,label,value,key):
    result=container.number_input(label,min_value=0.0,value=value/100 if value is not None else None,step=.01,key=key,placeholder='Pendiente')
    return cents(result) if result is not None else None


def printing_fields(d,prefix,scope):
    per_lot=scope=='Por lote'
    st.caption('Usa gramos y tiempo del lote completo.' if per_lot else 'Usa gramos y tiempo de una sola pieza.')
    a,b=st.columns(2)
    weight=d['grams']*d['lot_units'] if per_lot and d['grams'] is not None else d['grams']
    grams=a.number_input('Gramos del lote' if per_lot else 'Gramos por pieza',min_value=0.,max_value=1000000.,
        value=float(weight) if weight is not None else None,step=1.,key=prefix+'_grams_'+scope,placeholder='Del slicer')
    price=b.number_input('Precio por gramo · MXN/g',min_value=0.,max_value=10000.,
        value=d['material_rate_cents']/100000 if d['material_rate_cents'] is not None else None,step=.001,format='%.5f',key=prefix+'_gram_price',placeholder='Ej. 0.44')
    duration=d['lot_minutes'] if per_lot or d['lot_minutes'] is None else d['lot_minutes']/d['lot_units']
    a,b,c=st.columns(3)
    hours=a.number_input('Tiempo · horas',min_value=0,max_value=16666,value=int(duration//60) if duration is not None else None,
        step=1,key=prefix+'_hours_'+scope,placeholder='Ej. 2')
    mins=b.number_input('Tiempo · minutos',min_value=0.,max_value=59.999999,value=float(duration%60) if duration is not None else None,
        step=1.,format='%.2f',key=prefix+'_mins_'+scope,placeholder='Ej. 30')
    hourly=c.number_input('Tarifa de tiempo · MXN/h',min_value=0.,max_value=10000000.,
        value=d['machine_rate_cents']/100 if d['machine_rate_cents'] is not None else None,step=1.,key=prefix+'_hour_price',placeholder='Ej. 15')
    units=st.number_input('Piezas producidas en el lote',min_value=1,max_value=1000000,value=d['lot_units'],step=1,key=prefix+'_print_units') if per_lot else 1
    with st.expander('Costos adicionales y referencia',expanded=bool(d.get('fixed_cents'))):
        fixed=amount_field(st,'Adicional por pieza · MXN',d.get('fixed_cents') or 0,prefix+'_print_fixed')
        st.caption('Opcional. Incluye energía o desgaste en la tarifa por hora; evita sumarlos otra vez aquí.')
        notes=st.text_area('Notas de costeo',value=d['notes'],key=prefix+'_print_notes')
        source=st.text_input('Fuente o motivo *',value='Parámetros de impresión',key=prefix+'_print_source')
    minutes=(hours or 0)*60+(mins or 0) if hours is not None or mins is not None else None
    try:
        data=costing.printing_inputs(grams=grams,price_per_gram=price,minutes=minutes,hourly_rate=hourly,
            units=units,per_lot=per_lot,fixed_cents=fixed,notes=notes)
    except ValueError as exc:
        st.error(str(exc));data=None
    st.caption('Costo = gramos × MXN/g + (horas + minutos ÷ 60) × MXN/h.'+
        (' El material y el tiempo se dividen entre las piezas del lote.' if per_lot else ' Resultado por pieza.'))
    return data,source


def printing_result(data,result):
    with st.container(horizontal=True):
        for label,key in (('Material por pieza','material_cents'),('Tiempo por pieza','machine_cents'),('Costo por pieza','total_cents')):
            value=result[key]
            st.metric(label,money(value) if value is not None else 'Pendiente',border=True)
    if data['lot_units']>1 and result['total_cents'] is not None:
        st.caption(f"{data['lot_units']} piezas × {money(result['total_cents'])} = {money(result['total_cents']*data['lot_units'])} MXN por lote, con redondeo por pieza.")
    if result['fixed_cents']:st.caption('El total incluye '+money(result['fixed_cents'])+' MXN adicionales por pieza.')
    if result['missing']:st.info('Por completar: '+', '.join(result['missing']))


@managed_dialog('Costo de pieza',width='large')
def component_cost_form(component,profile,*,printing=False):
    d=profile['data'] if profile else costing.component_defaults(component['id'])
    purchased=costing.component_defaults(component['id'])['mode']=='Costo unitario'
    prefix='component_cost_'+st.session_state['dialog_request_key']
    with st.container(gap='xxsmall'):
        st.write(f"**{component['name']} · {component['variant']} · {component['material']}**")
        st.caption('Importes de costo sin IVA recuperable. Deja un dato vacío cuando no lo conozcas; 0 significa costo conocido de cero.')
        if profile:
            stored=costing.component_amount(d)['total_cents']
            st.badge('Costo guardado · '+(money(stored)+' MXN' if stored is not None else 'Pendiente'),color='gray')
            st.caption('Referencia actual: '+shorten(profile['source'],width=180,placeholder='…'))
    initial=costing.PRINT_MODE if printing and not purchased else d['mode']
    mode='Costo unitario' if purchased else st.selectbox('Cálculo',costing.MODES,index=costing.MODES.index(initial),key=prefix+'_mode')
    scope='Por pieza'
    if mode==costing.PRINT_MODE:
        scope=st.segmented_control('Datos del cálculo',('Por pieza','Por lote'),default='Por lote' if d['lot_units']>1 else 'Por pieza',key=prefix+'_scope', format_func=tag) or 'Por pieza'
    with st.form(prefix,border=mode!=costing.PRINT_MODE):
        if mode==costing.PRINT_MODE:
            with st.container(gap='xsmall'):data,source=printing_fields(d,prefix,scope)
        elif purchased:
            mode='Costo unitario';grams=rate=minutes=machine=fixed=None;units=1
            direct=amount_field(st,'Costo de compra por unidad · MXN',d['direct_cents'],prefix+'_direct')
            st.caption('Insumo comprado: captura el costo por una unidad física de cable, foco o empaque.')
        else:
            a,b=st.columns(2)
            grams=a.number_input('Gramos por pieza',min_value=0.,value=float(d['grams']) if d['grams'] is not None else None,key=prefix+'_grams')
            rate=amount_field(b,'Filamento · MXN/kg',d['material_rate_cents'],prefix+'_rate')
            a,b,c=st.columns(3)
            units=a.number_input('Piezas por lote',min_value=1,value=d['lot_units'],step=1,key=prefix+'_units')
            minutes=b.number_input('Minutos del lote completo',min_value=0.,value=float(d['lot_minutes']) if d['lot_minutes'] is not None else None,key=prefix+'_minutes')
            machine=amount_field(c,'Máquina · MXN/h',d['machine_rate_cents'],prefix+'_machine')
            a,b=st.columns(2)
            fixed=amount_field(a,'Costo fijo por pieza · MXN',d['fixed_cents'],prefix+'_fixed')
            direct=amount_field(b,'Costo unitario manual · MXN',d['direct_cents'],prefix+'_direct')
            st.caption('Material + fijo usa gramos × precio/kg ÷ 1,000 + fijo. Material + máquina agrega minutos del lote ÷ 60 × tarifa/h ÷ piezas. Costo unitario usa solo el importe manual. Evita incluir la máquina dos veces en el costo fijo.')
        if mode!=costing.PRINT_MODE:
            notes=st.text_area('Notas de costeo',value=d['notes'],key=prefix+'_notes')
            source=st.text_input('Fuente o motivo *',value='',placeholder='Slicer, factura de filamento, proveedor…',key=prefix+'_source')
            data=dict(mode=mode,grams=grams,lot_units=units,lot_minutes=minutes,material_rate_cents=rate,machine_rate_cents=machine,fixed_cents=fixed,direct_cents=direct,notes=notes)
        a,b=st.columns(2)
        preview=a.form_submit_button('Calcular costo')
        save=b.form_submit_button('Guardar costo de pieza',type='primary')
        if preview and data is not None:
            try:
                result=costing.component_amount(data)
                if mode==costing.PRINT_MODE:printing_result(data,result)
                else:st.info('Costo calculado: '+money(result['total_cents']) if result['total_cents'] is not None else 'Costos capturados: '+money(result['known_cents'])+' · Falta '+', '.join(result['missing']))
            except ValueError as exc:st.error(str(exc))
        if save and data is not None:perform(costing.save_component,component['id'],data,source=source,expected_id=profile['id'] if profile else None,message='Costo guardado en una nueva versión. Recetas actualizadas.')
    with st.expander('Versiones del costo de esta pieza'):
        entries=[]
        for version in costing.history('component',component['id']):
            amount=costing.component_amount(version['data'])['total_cents']
            entries.append(dict(version,cost=money(amount) if amount is not None else 'Pendiente'))
        table(entries,{'created_at':'Fecha','cost':'Costo unitario MXN','source':'Fuente'},label='Versiones anteriores de costo unitario')


@managed_dialog('Costos adicionales por producto',width='large')
def recipe_extras_form(rid,profile):
    data=profile['data'] if profile else {k:None for k in costing.EXTRAS}
    prefix='extras_'+st.session_state['dialog_request_key']
    included=costing.recipe_cost(rid).get('included_extra_keys',[])
    st.caption('Una unidad de producto terminado. Completa ensamble y otros costos; usa 0 solo cuando confirmes que no aplican o ya están incluidos.')
    with st.form(prefix):
        result={k:data.get(k) if k in included else amount_field(st,label+' · MXN',data.get(k),prefix+'_'+k) for k,label in costing.EXTRAS.items()}
        if included:st.caption('Cable, foco y empaque se costean como componentes de la lámpara y se suman una sola vez.')
        result['notes']=st.text_area('Notas',value=data.get('notes',''),key=prefix+'_notes')
        source=st.text_input('Fuente o motivo *',key=prefix+'_source')
        if st.form_submit_button('Guardar costos adicionales',type='primary'):
            perform(costing.save_extras,rid,result,source=source,expected_id=profile['id'] if profile else None,message='Costos adicionales guardados para esta versión de receta.')


def recipe_cost_panel(rid,key):
    report=costing.recipe_cost(rid)
    st.subheader('Costo de referencia por producto', icon=':material/calculate:')
    st.caption('Para cotizar: una impresión real factura su propio costo al asignarla, sin pedirlo otra vez aquí.')
    with st.container(horizontal=True):
        st.metric('Costo completo',money(report['total_cents']) if report['total_cents'] is not None else 'Pendiente',border=True)
        st.metric('Costos capturados',money(report['known_cents']),border=True)
    if report['missing']:st.warning('Por completar: '+' · '.join(report['missing']))
    table([dict(x,unit=money(x['total_cents']) if x['total_cents'] is not None else 'Pendiente',total=money(x['line_cents']) if x['line_cents'] is not None else 'Pendiente') for x in report['lines']],
        {'name':'Pieza','variant':'Variante','quantity':'Cantidad','unit':'Costo/pieza MXN','total':'Costo en receta MXN','source':'Referencia'},label='Costos de piezas de la receta')
    table([{'name':label,'amount':'Incluido en componentes' if k in report.get('included_extra_keys',[]) else money(report['extras'][k]) if report['extras'].get(k) is not None else 'Pendiente'} for k,label in costing.EXTRAS.items()],{'name':'Adicional por producto','amount':'MXN'},label='Kit, foco, empaque, ensamble y otros costos')
    if st.button('Editar costos adicionales',key=key+'_extras',icon=':material/edit:'):
        recipe_extras_form(rid,costing.extras_profile(rid))
    components={c['id']:c for c in recipes.load_catalog()['components'] if any(x['component_id']==c['id'] for x in report['lines'])}
    if components:
        cid=st.selectbox('Pieza a costear',list(components),format_func=lambda i:components[i]['name']+' · '+components[i]['variant'],key=key+'_component')
        if st.button('Editar costo de pieza',key=key+'_edit',icon=':material/edit:'):
            component_cost_form(components[cid],costing.component_profile(cid))
    st.caption('Las referencias de Sheets son aproximadas. Los márgenes usan costos congelados al asignarlos a la venta. Un costo posterior no cambia silenciosamente ventas anteriores.')
    return report


@managed_dialog('Asignar costos a la venta',width='large')
def sale_cost_form(sid,context):
    catalog=recipes.load_catalog();products={p['id']:p for p in catalog['products']}
    versions={v['id']:v for v in catalog['versions']}
    def label(i):
        if i is None:return 'Costo manual / pendiente'
        v=versions[i];p=products[v['product_id']]
        return f"{p['name']} · {p['variant']} · receta v{v['version']}"
    saved=context['prior']['data']['lines'] if context['prior'] and context['prior']['data']['sale_fingerprint']==context['fingerprint'] else []
    prefix='sale_cost_'+st.session_state['dialog_request_key']
    st.caption('Selecciona la receta real de cada partida. Una descripción genérica de Origen requiere identificar primero el modelo. El costeo usa el ingreso después del descuento y antes del IVA; los anticipos no son utilidad.')
    # Selectors outside the form let each recipe show its current preview before confirmation.
    assignments=[]
    for index,line in enumerate(context['data']['lines']):
        prior=saved[index] if index<len(saved) else {}
        st.write(f"**{index+1}. {line['description']} · {line['quantity']:g} unidades**")
        opts=[None,*versions]
        rid=st.selectbox('Receta de esta partida',opts,index=opts.index(prior.get('recipe_id')),format_func=label,key=prefix+f'_recipe_{index}')
        if rid:
            cost=costing.recipe_cost(rid)
            st.caption('Costo por unidad: '+money(cost['total_cents']) if cost['total_cents'] is not None else 'Costos incompletos: '+' · '.join(cost['missing']))
            assignments.append(dict(recipe_id=rid,recipe_fingerprint=cost['fingerprint']))
        else:
            manual=amount_field(st,'Costo unitario manual · MXN',prior.get('unit_cost_cents'),prefix+f'_manual_{index}')
            assignments.append(dict(recipe_id=None,manual_cents=manual))
    with st.form(prefix):
        source=st.text_input('Motivo o referencia del costeo *',key=prefix+'_source')
        if st.form_submit_button('Guardar costeo de venta',type='primary'):
            perform(costing.assign_sale,sid,assignments,expected_fingerprint=context['fingerprint'],
                expected_id=context['prior']['id'] if context['prior'] else None,source=source,message='Costeo congelado en la venta. Historial anterior conservado.')


def sale_cost_panel(sid):
    report=costing.sale_margin(sid)
    st.subheader('Utilidad bruta estimada', icon=':material/trending_up:')
    a,b,c=st.columns(3)
    a.metric('Venta neta sin IVA',money(report['net_revenue_cents']),border=True)
    b.metric('Costo directo',money(report['cost_cents']) if report['complete'] else 'Pendiente',border=True)
    c.metric('Utilidad bruta',money(report['profit_cents']) if report['complete'] else 'Pendiente',border=True)
    if report['margin_percent'] is not None:st.caption(f"Margen sobre venta neta: {report['margin_percent']:.1f}%")
    if report['stale']:st.warning('Cambió el contenido de la venta. Revisa sus partidas y vuelve a asignar costos.')
    elif not report['complete']:st.info('Completa los costos y asigna una receta o costo unitario a cada partida para calcular la utilidad.')
    if report['context']['prior']:st.caption('Costeo guardado: '+report['context']['prior']['created_at']+' · '+report['context']['prior']['source'])
    table([dict(x,unit=money(x['unit_cost_cents']) if x['unit_cost_cents'] is not None else 'Pendiente',cost=money(x['cost_cents']) if x['cost_cents'] is not None else 'Pendiente') for x in report['rows']],
        {'description':'Partida','quantity':'Cantidad','unit':'Costo unitario MXN','cost':'Costo total MXN'},label='Costos congelados de las partidas vendidas')
    if report['context']['sale']['status']=='Activa' and st.button('Asignar / actualizar costeo',key=f'sale_cost_edit_{sid}',icon=':material/edit:'):
        sale_cost_form(sid,report['context'])
    with st.expander('Historial del costeo de esta venta'):
        for version in costing.history('sale',sid):
            st.write(f"**{version['created_at']} · {version['source']}**")
            table([dict(x,cost=money(x['cost_cents']) if x['cost_cents'] is not None else 'Pendiente') for x in version['data']['lines']],
                {'description':'Partida','quantity':'Cantidad','cost':'Costo total MXN'},label='Partidas de una versión anterior de costeo')
    st.caption('Utilidad bruta estimada = venta neta sin IVA − costos directos capturados. Renta, administración y otros gastos generales quedan fuera; no es utilidad neta ni saldo de caja.')


@managed_dialog('Usar costo de impresión en recetas',width='medium')
def job_cost_form(reference):
    st.write(f"**{reference['code']} · {reference['quantity']} piezas en el lote**")
    st.caption('Los gramos y minutos guardados son del lote completo y se reparten entre sus piezas. Esta acción crea una referencia nueva para la pieza del catálogo; los costos guardados en ventas se conservan.')
    with st.form('job_cost_reference'):
        fixed=amount_field(st,'Otros costos fijos por pieza · MXN',None,'job_cost_fixed')
        source=st.text_input('Fuente o motivo *',value=reference['code']+' · estimación del lote')
        if st.form_submit_button('Publicar costo para recetas',type='primary'):
            perform(costing.publish_job_cost,reference['job_id'],expected_revision=reference['revision'],expected_job_revision=reference['job_revision'],expected_profile_id=reference['profile_id'],fixed_cents=fixed,source=source,message='Costo del lote publicado para la pieza del catálogo.')
