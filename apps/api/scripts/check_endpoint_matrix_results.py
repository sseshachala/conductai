"""Reject a green pytest report that contains no completed endpoint probes."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.etree import ElementTree

ROLES = {"admin", "security", "developer", "viewer"}
PROBE_NAME = re.compile(r"test_rbac_matrix\[(.+)-(admin|security|developer|viewer)\]$")


def check_report(path: Path) -> int:
    report = ElementTree.parse(path)
    probes = [
        case for case in report.iter("testcase")
        if case.get("classname", "").endswith("test_endpoint_matrix")
        and case.get("name", "").startswith("test_rbac_matrix[")
    ]
    if not probes:
        raise ValueError("Endpoint matrix executed zero probes")
    incomplete = [
        case.get("name", "") for case in probes
        if any(case.find(status) is not None for status in ("skipped", "failure", "error"))
    ]
    if incomplete:
        raise ValueError(f"Endpoint matrix has {len(incomplete)} incomplete probe(s)")
    route_roles: dict[str, set[str]] = {}
    for case in probes:
        match = PROBE_NAME.fullmatch(case.get("name", ""))
        if match is None:
            raise ValueError("Endpoint matrix probe is missing its route/role identity")
        route, role = match.groups()
        seen = route_roles.setdefault(route, set())
        if role in seen:
            raise ValueError("Endpoint matrix contains a duplicate route/role probe")
        seen.add(role)
    if any(roles != ROLES for roles in route_roles.values()):
        raise ValueError("Endpoint matrix has incomplete four-role coverage")
    return len(probes)


def main() -> int:
    try:
        count = check_report(Path(sys.argv[1]))
    except (IndexError, OSError, ElementTree.ParseError, ValueError) as exc:
        print(f"Endpoint matrix coverage failed: {exc}", file=sys.stderr)
        return 1
    print(f"Endpoint matrix: {count} real route/role probes passed, zero skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
