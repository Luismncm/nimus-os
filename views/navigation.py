import streamlit as st


def select_order(order_id: int) -> None:
    st.session_state["open_order_id"] = order_id


def open_order(order_id: int) -> None:
    select_order(order_id)
    st.session_state.pop("focus_item_id", None)
    st.switch_page("views/orders.py")


def focus_item(item_id: int) -> None:
    st.session_state["focus_item_id"] = item_id
    st.session_state["pending_focus_item"] = item_id


def focus_part(item_id: int, part_id: int) -> None:
    focus_item(item_id)
    st.session_state['focus_part_id'] = part_id


def focus_assign(part: dict) -> None:
    """The order's Asignar view with this piece picked: the one place where any piece is assigned."""
    oid = part['order_id']
    st.session_state.update({f'order_detail_tabs_{oid}': 'Producción', f'order_production_view_{oid}': 'Asignar',
                             f'order_assign_{oid}_piece': part['id'], f'order_assign_{oid}_material': None})


def open_assign(part: dict) -> None:
    """From another page: open the order on its Asignar view with this piece picked."""
    focus_assign(part)
    st.session_state['open_order_id'] = part['order_id']
    st.session_state.pop('focus_item_id', None)
    st.switch_page('views/orders.py')


def open_queue(order_id: int | None = None, machine_id: int | None = None) -> None:
    st.session_state["queue_focus"] = {"order_id": order_id, "machine_id": machine_id}
    st.switch_page("views/queue.py")
