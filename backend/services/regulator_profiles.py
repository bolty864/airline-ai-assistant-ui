"""Regulators the platform supports, with the lens GPT-4o should read their changes through."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RegulatorProfile:
    code: str
    name: str
    focus: str


PROFILES: dict[str, RegulatorProfile] = {p.code: p for p in [
    RegulatorProfile("DGCA", "Directorate General of Civil Aviation (India)",
                     "Civil Aviation Requirements (CARs): flight operations, crew training and licensing, airworthiness, "
                     "safety management, record keeping and passenger data (API/PNR) obligations."),
    RegulatorProfile("BCAS", "Bureau of Civil Aviation Security (India)",
                     "Aviation security: screening, access control to airside, security programmes, background checks, "
                     "incident reporting to the security authority."),
    RegulatorProfile("CERT-IN", "Indian Computer Emergency Response Team",
                     "Cyber security directions: incident reporting within hours, log retention, clock synchronisation, "
                     "vulnerability management, point of contact obligations."),
    RegulatorProfile("DPDP", "Digital Personal Data Protection Act (India)",
                     "Personal data protection: consent, notice, purpose limitation, data principal rights, breach "
                     "notification, retention limits and erasure, children's data, significant data fiduciary duties."),
    RegulatorProfile("ICAO", "International Civil Aviation Organization",
                     "Annexes and SARPs: safety, security, facilitation (passenger data), safety management systems. "
                     "State-level standards that DGCA transposes."),
    RegulatorProfile("IATA", "International Air Transport Association",
                     "Industry standards: IOSA audit standards, ticketing and distribution, dangerous goods, passenger "
                     "data exchange standards."),
]}

_ALIASES = {"CERTIN": "CERT-IN", "DPDPA": "DPDP", "DPDPACT": "DPDP", "DIGITALPERSONALDATAPROTECTION": "DPDP"}


def resolve_regulator(regulator: str | None) -> RegulatorProfile | None:
    """'cert_in', 'CERT-In', 'dgca' ... -> profile. None for a regulator the platform does not know."""
    compact = re.sub(r"[^A-Z]", "", (regulator or "").upper())
    code = _ALIASES.get(compact, compact)
    if code == "CERTIN":
        code = "CERT-IN"
    return PROFILES.get(code)
