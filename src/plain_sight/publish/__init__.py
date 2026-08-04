"""The publish gate: the one-way step from system-of-record to public artifact.

This is the single enforcement point for **verified-only**. It reads the
repository, keeps only ``verified`` rows, and emits sanitised **static HTML** so
that unverified/pending claims are *physically absent* from the output, not
merely filtered by a live query. Postgres never faces the public: the artifact
is pre-rendered here and shipped to a static host.
"""

from __future__ import annotations

from plain_sight.publish.site import (
    Freshness,
    MemberPage,
    PublishedClaim,
    build_member_page,
    publish_member,
    render_member_page,
)

__all__ = [
    "Freshness",
    "MemberPage",
    "PublishedClaim",
    "build_member_page",
    "publish_member",
    "render_member_page",
]
