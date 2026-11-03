"""Isolated Streamlit v2 component; untrusted values are rendered as text."""
import streamlit as st
from services.board_moves import token
from services.order_board import LANES
from views.board_forms import board_move_form
from views.navigation import open_order
from utils.dates import fmt
from services.order_progress import manufacturing, supplies, fabrication_label

CSS='''
/* Five lanes fit a 1440 px screen beside the sidebar; narrower screens scroll the board sideways. */
.board {display:grid;grid-template-columns:repeat(5,minmax(200px,1fr));gap:12px;overflow-x:auto;padding:4px 2px 16px;font-family:var(--st-font);color:var(--st-text-color)}
.lane {border:1px solid var(--st-border-color);border-radius:var(--st-base-radius);background:var(--st-secondary-background-color);min-width:200px}
.lane.dragover {outline:3px solid var(--st-primary-color);outline-offset:-3px}
.lane h3 {margin:0;padding:13px 14px 4px;font-size:15px;border-top:4px solid var(--accent);border-radius:var(--st-base-radius) var(--st-base-radius) 0 0;display:flex;align-items:center;gap:8px}
.lane h3 .count {font-size:12px;font-weight:700;color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent);border-radius:99px;padding:1px 8px;font-variant-numeric:tabular-nums}
.hint {padding:0 14px 10px;margin:0;font-size:11.5px;opacity:.75;min-height:28px}
.stack {min-height:140px;max-height:72vh;overflow-y:auto;overscroll-behavior:contain;padding:0 8px 12px;display:flex;flex-direction:column;gap:12px}
.card {background:var(--st-background-color);border:1px solid var(--st-border-color);border-left:4px solid var(--tone,var(--st-border-color));border-radius:var(--st-base-radius);padding:12px 10px 10px;box-shadow:0 2px 5px rgba(0,0,0,.035);cursor:grab}
.card.origin {background:#FFFCF3}
.code {display:inline-flex;align-items:center;gap:6px;white-space:nowrap;font-weight:700;color:var(--tone);background:color-mix(in srgb,var(--tone) 12%,transparent);border:1px solid color-mix(in srgb,var(--tone) 35%,transparent);border-radius:99px;padding:2px 9px}
.code::before {content:"";width:7px;height:7px;border-radius:50%;background:var(--dot,var(--tone))}
.code.origin {color:#E2C275;background:#1F1C17;border-color:#B8902F}
.card[draggable=false] {cursor:default}
.card.dragging {opacity:.45}
.card:focus-visible,button:focus-visible,select:focus-visible {outline:3px solid var(--st-primary-color);outline-offset:2px}
.top {display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:11.5px;margin-bottom:6px}
.dest {color:var(--st-gray-text-color);font-weight:600;text-transform:uppercase;letter-spacing:.04em;font-size:10.5px}
.title {font-size:15px;font-weight:650;line-height:1.3;margin:0 0 2px;overflow-wrap:anywhere}
.meta {font-size:12px;margin:4px 0;overflow-wrap:anywhere;color:var(--st-gray-text-color)}
.flags {display:flex;flex-wrap:wrap;gap:4px;margin:6px 0 4px}.flags .flag {margin:0}
.next {font-size:12.5px;font-weight:650;margin:8px 0 0;padding:6px 8px;border-radius:8px;background:color-mix(in srgb,var(--tone) 9%,transparent);color:var(--st-text-color);overflow-wrap:anywhere}
.next::before {content:"→ ";color:var(--tone)}
.flag {display:inline-block;padding:2px 7px;border-radius:6px;font-size:11px;font-weight:600;background:var(--st-gray-background-color);color:var(--st-gray-text-color);margin:3px 4px 3px 0}
.red {background:var(--st-red-background-color);color:var(--st-red-text-color)}
.orange {background:var(--st-orange-background-color);color:var(--st-orange-text-color)}
progress {width:100%;height:6px;accent-color:var(--tone,var(--st-primary-color));margin-top:4px}
button,select {font:inherit;font-size:13px;color:var(--st-text-color);border:1px solid var(--st-border-color);background:var(--st-background-color);border-radius:var(--st-button-radius);padding:7px 10px;min-height:36px;cursor:pointer;-webkit-tap-highlight-color:transparent}
.open {flex:1;font-weight:600;background:var(--st-primary-color);color:var(--st-background-color);border-color:var(--st-primary-color)}
/* Hover only where a pointer can hover: on a tablet a tapped card or button would stay lit. */
@media (hover:hover) {
 button:hover {border-color:var(--st-primary-color);color:var(--st-primary-color)}
 .open:hover {color:var(--st-background-color);filter:brightness(1.12)}
}
.actions {display:flex;gap:6px;margin-top:8px}
.move {display:flex;gap:6px;margin-top:6px}.move select {min-width:0;flex:1;padding-inline:8px}.move button {padding-inline:8px}
.empty {font-size:13px;padding:18px 5px;text-align:center}.status {font-size:12px;padding:5px 0;min-height:18px}
button:disabled {cursor:wait;opacity:.65}
@media (prefers-reduced-motion:no-preference) {
 .board:not(.reduce-motion) .card {transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease,opacity .16s ease}
 .board:not(.reduce-motion) button {transition:filter .15s ease-out,scale .15s ease-out}
 .board:not(.reduce-motion) button:not(:disabled):active {scale:.96}
}
@media (prefers-reduced-motion:no-preference) and (hover:hover) {
 .board:not(.reduce-motion) .card:not(.dragging):hover {transform:translateY(-2px);box-shadow:0 7px 18px rgba(0,0,0,.08);border-color:var(--st-primary-color)}
}
@media (prefers-reduced-motion:no-preference) {
 .board:not(.reduce-motion) .lane {transition:outline-color .16s ease}
 .board:not(.reduce-motion) progress::-webkit-progress-value {transition:width .2s ease}
}
'''
JS='''
export default function(component) {
 const {parentElement,data,setTriggerValue}=component;
 const root=parentElement.querySelector('.board');
 root.classList.toggle('reduce-motion',Boolean(data.reduce_motion));
 const status=parentElement.querySelector('.status');
 root.replaceChildren();root.setAttribute('aria-busy','false');status.textContent='';
 let dragged=null,waiting=false;
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==null)n.textContent=text;if(cls)n.className=cls;return n;};
 const emit=(card,target)=>{
   if(waiting||target===card.lane)return;
   waiting=true;status.textContent='Validando movimiento…';root.setAttribute('aria-busy','true');
   root.querySelectorAll('button').forEach(button=>button.disabled=true);
   setTriggerValue('move',{id:card.id,target,token:card.token});
 };
 for(const lane of data.lanes){
   const section=el('section',null,'lane');section.setAttribute('aria-label','Etapa '+lane.label);
   section.style.setProperty('--accent','var(--st-'+lane.color+'-color)');
   const cards=data.cards.filter(c=>c.lane===lane.label);
   const head=el('h3',lane.label);head.append(el('span',String(cards.length),'count'));section.append(head,el('p',lane.hint,'hint'));
   section.ondragover=e=>{if(dragged){e.preventDefault();e.dataTransfer.dropEffect='move';section.classList.add('dragover');}};
   section.ondragleave=e=>{if(!section.contains(e.relatedTarget))section.classList.remove('dragover');};
   section.ondrop=e=>{e.preventDefault();section.classList.remove('dragover');if(dragged)emit(dragged,lane.label);};
   const stack=el('div',null,'stack');section.append(stack);
   if(!cards.length)stack.append(el('p','Suelta un pedido aquí','empty'));
   for(const card of cards){
     const article=el('article',null,'card'+(card.origin?' origin':''));article.draggable=!card.closed;article.tabIndex=0;
     article.style.setProperty('--tone',card.tone);article.style.setProperty('--dot',card.dot);
     article.setAttribute('aria-label',card.code+' · '+card.title);
     article.ondragstart=e=>{if(card.closed||waiting){e.preventDefault();return;}dragged=card;e.dataTransfer.setData('text/plain',String(card.id));e.dataTransfer.effectAllowed='move';article.classList.add('dragging');};
     article.ondragend=()=>{dragged=null;article.classList.remove('dragging');root.querySelectorAll('.dragover').forEach(n=>n.classList.remove('dragover'));};
     const top=el('div',null,'top');top.append(el('span',card.code,'code'+(card.origin?' origin':'')),el('span',card.destination,'dest'));
     article.append(top,el('h4',card.title,'title'),el('p',(card.client||'Sin cliente')+' · '+card.products+(card.products===1?' producto':' productos'),'meta'));
     const flags=el('div',null,'flags');
     if(card.blocked)flags.append(el('span','Bloqueado','flag red'));
     if(card.overdue)flags.append(el('span','Atrasado','flag red'));
     else if(card.today)flags.append(el('span','Entrega hoy','flag orange'));
     if(card.priority==='Alta')flags.append(el('span','Alta prioridad','flag orange'));
     flags.append(el('span',card.date,'flag'));
     article.append(flags);
     if(card.required){
       const progress=el('progress',null);progress.max=100;progress.value=card.progress;progress.setAttribute('aria-label','Fabricación '+card.progress+'%');
       article.append(progress);
     }
     article.append(el('p',card.fabrication,'meta'));
     if(card.supplies_required)article.append(el('span','Insumos '+card.supplies_covered+'/'+card.supplies_required+(card.supplies_remaining?' · faltan '+card.supplies_remaining:' cubiertos'),'flag'+(card.supplies_remaining?' orange':'')));
     if(card.from_stock)article.append(el('p','De inventario · '+card.from_stock+' piezas','meta'));
     article.append(el('p',card.action,'next'));
     const open=el('button','Abrir','open');open.type='button';open.setAttribute('aria-label','Abrir '+card.code);open.onclick=()=>{if(!waiting){waiting=true;open.disabled=true;setTriggerValue('open',card.id);}};
     const actions=el('div',null,'actions');actions.append(open);article.append(actions);
     if(!card.closed){
       const move=el('div',null,'move'),select=el('select',null);
       select.setAttribute('aria-label','Mover '+card.code+' a otra etapa');
       for(const target of data.lanes){if(target.label===card.lane)continue;const option=el('option',target.label);option.value=target.label;select.append(option);}
       if(card.next)select.value=card.next;
       const button=el('button','Mover');button.type='button';button.onclick=()=>emit(card,select.value);move.append(select,button);article.append(move);
     }
     stack.append(article);
   }
   root.append(section);
 }
}
'''
HTML='''
<div class="status" role="status" aria-live="polite"></div>
<div class="board" aria-label="Tablero de pedidos"></div>
'''
_BOARD=st.components.v2.component('nimus_order_kanban',html=HTML,css=CSS,js=JS)

def mount(data):
    global _BOARD
    from streamlit.errors import StreamlitAPIException
    try:
        return _BOARD(data=data,key='orders_kanban',on_move_change=lambda:None,on_open_change=lambda:None)
    except StreamlitAPIException as exc:
        if 'is not registered' not in str(exc): raise
        # AppTest replaces the runtime between apps while Python retains imports.
        # Register once in the new runtime; normal reruns keep the module renderer.
        _BOARD=st.components.v2.component('nimus_order_kanban',html=HTML,css=CSS,js=JS)
        return _BOARD(data=data,key='orders_kanban',on_move_change=lambda:None,on_open_change=lambda:None)

NEXT={'Planificar':'Producir','Producir':'Preparar','Preparar':'Salida','Salida':'Entregados'}
NEXT_PROTOTYPE={'Planificar':'Producir','Producir':'Entregados','Entregados':'Planificar'}

def render(rows):
    from views.kind_style import order_kind, order_tone, IDENTITY
    cards=[]
    for o in rows:
        # The same color as the order's card and prints elsewhere: its own, Colección Origen gold on black, stock blue.
        kind=order_kind(o)
        t=o['tracking']
        m, s = manufacturing(o), supplies(o)
        # Prototypes move too: to Producir starts a print, to Entregados finishes them and closes the project, back reopens it.
        cards.append(dict(id=o['id'],token=token(o),code=o['code'],title=o['project'],client=o['client'] or ('Desarrollo' if kind=='Prototipo' else ''),
            lane=t['lane'],closed=t['delivered'] and kind!='Prototipo',next=NEXT_PROTOTYPE.get(t['lane']) if kind=='Prototipo' else NEXT.get(t['lane']),blocked=t['blocked'],overdue=t['overdue'],today=t['due_today'],
            destination='Prototipo' if kind=='Prototipo' else 'Origen' if kind=='Origen' else 'Stock' if o.get('fulfillment')=='Stock' else 'Cliente',priority=o['priority'],
            tone=order_tone(o['id'],kind)[1],dot=IDENTITY[o['id']%len(IDENTITY)],origin=kind=='Origen',
            date=('Cerrado · '+fmt(o['updated_at'])) if t['delivered'] else ('Entrega · '+fmt(o['deadline']) if o['deadline'] else 'Sin fecha de entrega'),
            progress=m['progress'],required=m['required'],completed=m['completed'],fabrication=fabrication_label(o),
            supplies_required=s['required'],supplies_covered=s['covered'],supplies_remaining=s['remaining'],
            from_stock=o.get('manufactured_from_stock',0),products=t['products'],action=t['action']))
    lanes=[dict(label=label,color=color,hint=hint) for label,(_,color,hint) in LANES.items()]
    lanes.append(dict(label='Entregados',color='gray',hint='Histórico de entregas y lotes liberados.'))
    # Acknowledge a handled trigger even when the order itself did not change.
    # CCv2 reruns JavaScript when data changes; this resets the local click lock
    # before a dismissed dialog returns to the same board.
    ack=st.session_state.get('kanban_ack',0)
    result=mount(dict(cards=cards,lanes=lanes,reduce_motion=bool(st.session_state.get('ui_reduce_motion',False)),ack=ack))
    if result.open in {o['id'] for o in rows}:
        st.session_state['kanban_ack']=ack+1
        open_order(result.open)
    move=result.move
    if isinstance(move,dict):
        allowed={o['id']:o for o in rows}
        if move.get('id') in allowed and move.get('target') in (*LANES,'Entregados') and isinstance(move.get('token'),str):
            st.session_state['kanban_ack']=ack+1
            board_move_form(move['id'],move['target'],move['token'])
