"""Judge-authored mandates, compiled at runtime and enforced unsigned.

A judge types an intent, the compiler turns it into clauses, and the same
`Gateway` that serves the signed mandate enforces those clauses against real
proposals. The point of the feature is that it is *their* sentence doing the
refusing, not a demo script.

**The policy is unsigned, and the gateway refusing to sign it is the feature.**
Signing at runtime would need the issuer private key inside the service, which
contradicts decision 2 (the issuer is an offline CLI, never a daemon) and would
fail `test_docker_image_ships_no_signing_key`. So a sandbox policy is a `Policy`
built in memory and never written to disk. That is not a promise anybody has to
keep: `Policy` has no signature field at all — signatures live beside the
document in the YAML and are checked by `policy.loader`, which nothing here
calls. A sandbox policy is structurally unsigned rather than politely unsigned.

**Why one reserved mandate id and not one per session.** `Gateway._verify_token`
requires `claims.mandate_id == policy.mandate_id`, and that check is not
negotiable — relaxing it for a demo would put a hole in the boundary the whole
project is about. Tokens are minted offline, so the id a sandbox token is bound
to has to be known before any judge types anything. Hence one reserved id for
every sandbox, with sessions kept apart by `jti` exactly as they already are.

The consequence to know: an audit record from a sandbox says `mnd_sandbox_01`,
which is deliberately *not* the signed mandate's id. A reader can tell at a
glance whether a decision came from the signed document or from something a
visitor typed, and no sandbox order can be mistaken for the real mandate's.
"""
from mandate.policy.models import Policy

#: The mandate id every sandbox policy is rebound to. Sandbox tokens are minted
#: offline against this id; see the module docstring for why it is one id and
#: not one per session.
SANDBOX_MANDATE_ID = "mnd_sandbox_01"

#: jti prefix for the sandbox token pool. It must differ from the main pool's
#: `tok_pool`, because `SessionManager` keys sessions on jti and rmtree's the
#: session directory on create — a colliding jti would delete a live session's
#: audit chain rather than merely confuse it.
SANDBOX_JTI_PREFIX = "tok_sbx"

#: What a person would run to turn their sandbox policy into a real one. Shown
#: on the page beside the unsigned badge, because "we cannot sign this here" is
#: only half an answer without "here is where it is signed".
SIGN_COMMAND = "mandate compile 'your intent' --out policies/yours.yaml && mandate sign policies/yours.yaml"


def to_sandbox_policy(compiled: Policy) -> Policy:
    """Rebind a freshly compiled policy to the reserved sandbox mandate.

    The clauses, the provenance and the user's own `source_text` are untouched:
    what a judge typed is what gets enforced, and rewriting any of it would make
    the demo a puppet show. Only the identity changes, so that an offline-minted
    sandbox token binds and so that nothing downstream confuses this with the
    signed mandate.
    """
    return compiled.model_copy(update={"mandate_id": SANDBOX_MANDATE_ID})


def is_sandbox(policy: Policy) -> bool:
    return policy.mandate_id == SANDBOX_MANDATE_ID


__all__ = [
    "SANDBOX_JTI_PREFIX",
    "SANDBOX_MANDATE_ID",
    "SIGN_COMMAND",
    "is_sandbox",
    "to_sandbox_policy",
]
