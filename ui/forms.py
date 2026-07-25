"""Generic Streamlit form rendering from strategy metadata."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Iterable, Mapping

import streamlit as st

from core.strategy import ParamSpec, ParamType


def render_strategy_params(
    specs: Iterable[ParamSpec],
    *,
    key_prefix: str,
    exclude: Iterable[str] = (),
    defaults: Mapping[str, Any] | None = None,
) -> dict:
    excluded = set(exclude)
    overrides = dict(defaults or {})
    visible = [spec for spec in specs if spec.name not in excluded]
    params: dict[str, Any] = {}

    for advanced, container in (
        (False, st.container()),
        (True, st.expander("Advanced controls", expanded=False)),
    ):
        grouped: dict[str, list[ParamSpec]] = {}
        for spec in visible:
            if spec.advanced == advanced:
                grouped.setdefault(spec.group, []).append(spec)
        if not grouped:
            continue
        with container:
            for group, group_specs in grouped.items():
                if len(grouped) > 1 or group != "Basic":
                    st.caption(group.upper())
                for spec in group_specs:
                    params[spec.name] = _render_param(
                        spec,
                        key=f"{key_prefix}_{spec.name}",
                        value=overrides.get(spec.name, spec.default),
                    )
    return params


def _render_param(spec: ParamSpec, *, key: str, value: Any) -> Any:
    help_text = spec.help or None
    required = " *" if spec.required else ""
    label = f"{spec.label}{required}"

    if spec.type == ParamType.BOOL:
        return st.checkbox(label, value=bool(value), help=help_text, key=key)
    if spec.type == ParamType.ENUM:
        choices = spec.choices or []
        index = choices.index(value) if value in choices else None
        return st.selectbox(
            label,
            choices,
            index=index,
            help=help_text,
            key=key,
            placeholder="Select an option",
        )
    if spec.type in (ParamType.INT, ParamType.FLOAT):
        number_value = value
        kwargs: dict[str, Any] = {
            "label": label,
            "value": number_value,
            "help": help_text,
            "key": key,
        }
        if spec.min is not None:
            kwargs["min_value"] = (
                int(spec.min) if spec.type == ParamType.INT else float(spec.min)
            )
        if spec.max is not None:
            kwargs["max_value"] = (
                int(spec.max) if spec.type == ParamType.INT else float(spec.max)
            )
        kwargs["step"] = 1 if spec.type == ParamType.INT else 0.1
        return st.number_input(**kwargs)
    if spec.type == ParamType.DATE:
        parsed = date.fromisoformat(str(value)) if value else date.today()
        return st.date_input(label, value=parsed, help=help_text, key=key).isoformat()
    if spec.type == ParamType.TEXT:
        return st.text_area(label, value=value or "", help=help_text, key=key)
    if spec.type == ParamType.SYMBOLS:
        if isinstance(value, (list, tuple)):
            value = ", ".join(map(str, value))
        return st.text_input(label, value=value or "", help=help_text, key=key)
    if spec.type == ParamType.JSON:
        payload = (
            "" if value in (None, []) else json.dumps(value, indent=2, default=str)
        )
        raw = st.text_area(label, value=payload, help=help_text, key=key)
        if not raw.strip():
            return spec.default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            st.error(f"{spec.label} must be valid JSON.")
            return raw
    return st.text_input(label, value=value or "", help=help_text, key=key)
