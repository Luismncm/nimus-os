"""One calculation shared by the finance modules.

The money pages are reached from the sidebar's Control financiero group, in the same order and with the
same names; they no longer repeat that list as a strip under each title.
"""
import streamlit as st
from services import cash_projection
from services.quotations import money
from utils.dates import now


def open_account(account_id):
    """Jump to Tesorería → Movimientos, filtered to this account's own history."""
    st.session_state.update(treasury_account_filter=account_id, treasury_tabs='Movimientos', treasury_filters_open=True)
    st.switch_page('views/treasury.py')


def money_header(key):
    """The money summary in one line, for the finance pages that are not the summary itself.

    The full summary (cards, planned expenses, balance reconciliation and where the money is) lives in
    Resumen y previsión; here the same three figures read in one line, with the way there.
    """
    day=st.session_state.get('budget_month') or now().date()
    report,result=cash_projection.workspace(day.strftime('%Y-%m'))
    total,after=result['cash']['total_cents'],result['after_cents']
    with st.container(border=True,horizontal=True,vertical_alignment='center',gap='medium',key=f'panel-money-{key}'):
        for label,value in (('Total en cuentas',total),('Gastos proyectados',result['projected_cents']),('Después de gastos',after)):
            st.markdown(f":gray[{label}] **{money(value) if value is not None else '—'}**",width='content')
        if after is not None:
            st.badge('Disponible proyectado' if after>=0 else 'Faltan '+money(-after),color='green' if after>=0 else 'orange')
        st.space('stretch')
        st.page_link('views/budget.py',label='Resumen y previsión',icon=':material/arrow_forward:',
                     help=f"Cuentas, gastos previstos y conciliación de saldos · previsión de {report['month']}.")
    return result
