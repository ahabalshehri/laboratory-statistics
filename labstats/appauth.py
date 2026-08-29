"""Lightweight password gate for the Streamlit app.

Local runs: no password is configured, so `require_password()` is a no-op.
Hosted runs (Streamlit Community Cloud): set an `app_password` secret and the
app prompts for it before rendering anything.
"""
from __future__ import annotations

import hmac

import streamlit as st

_SESSION_KEY = "_authenticated"


def _configured_password() -> str | None:
    try:
        value = st.secrets.get("app_password")
    except Exception:  # no secrets file at all (local dev)
        return None
    return str(value) if value else None


def is_hosted() -> bool:
    """True on a shared deployment (an `app_password` secret is set)."""
    return _configured_password() is not None


def require_password() -> None:
    expected = _configured_password()
    if not expected:
        return  # open (local / dev)
    if st.session_state.get(_SESSION_KEY):
        return

    st.markdown("### 🔒 This deployment is protected")
    st.caption("Enter the access password to continue.")
    with st.form("login", clear_on_submit=False):
        pw = st.text_input("Password", type="password", label_visibility="collapsed")
        if st.form_submit_button("Enter"):
            if hmac.compare_digest(pw, expected):
                st.session_state[_SESSION_KEY] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()
