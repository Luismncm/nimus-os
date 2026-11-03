"""Shared numeric tables and record shortcuts for financial views."""
import pandas as pd
import streamlit as st
from views.work_context import open_record
from utils.csv_export import amount, csv_bytes


def table_csv(rows,columns,amount_fields=()):
    return csv_bytes(list(columns.values()),([amount(row.get(k)) if k in amount_fields else str(row.get(k) or '') for k in columns] for row in rows))


def financial_table(rows,columns,amount_fields,*,label,open=None,key=None):
    """Amounts in pesos; with open, a picked row opens its record (see views.common.dataframe)."""
    if not rows:
        st.info('Sin registros con esta selección.')
        return
    from views.emoji import STATE_COLUMNS, status
    from views.common import dataframe
    frame=pd.DataFrame(rows).reindex(columns=list(columns))
    for field in STATE_COLUMNS:
        if field in frame: frame[field]=frame[field].map(status)
    for field in amount_fields: frame[field]=frame[field].map(lambda v:v/100 if pd.notna(v) else None)
    frame=frame.rename(columns=columns)
    config={columns[f]:st.column_config.NumberColumn(columns[f],format='$%.2f') for f in amount_fields}
    dataframe(frame,rows,label=label,config=config,open=open,key=key)


def opens(kind,field='id'):
    """The usual open: the row's record of this kind, by the row's own id or a linked one."""
    return lambda row: open_record(kind,row[field])


def money_pulse(cards,*,key='money'):
    """A page's headline figures as metric cards with a colored left edge by urgency: (label, value, tone[, help]).

    tone is 'calm' (the environment's own accent), 'orange' or 'red' — real st.metric widgets underneath,
    so every page still reads and tests the same way; only the edge gives it the organic, alive feel.
    """
    cols=st.columns(len(cards))
    for index,(col,card) in enumerate(zip(cols,cards)):
        label,value,tone=card[:3]
        help_text=card[3] if len(card)>3 else None
        with col,st.container(key=f'mcard-{tone}-{key}-{index}'):
            st.metric(label,value,border=True,help=help_text)
