#!/usr/bin/env python3
"""Désactive les comptes TB dont l'attribut `expiration_ts` (SERVER_SCOPE)
est échu. Idempotent : ne retouche pas un compte déjà désactivé (état réel,
attribut `deactivated`).

Cron quotidien (cf. deploy/tb-notify.cron). Action = même mécanisme que le
bouton "Désactiver" de la webapp (`webapp.py:_set_account_active`) :
  - `tb.set_credentials_enabled(uid, False)` → coupe réellement le login
    (colonne `user_credentials.enabled`, la seule que TB lit pour bloquer
    l'authentification — PAS `additionalInfo`, qui est un champ calculé
    lecture-seule côté serveur et un no-op complet en écriture).
  - `deactivated=True` en SERVER_SCOPE → coupe aussi le routage des mails de
    défaut (`common.py:_collect_user_attrs`, routage `deactivated`-only).

Ne touche JAMAIS un compte dont `authority != CUSTOMER_USER` : le formulaire
d'expiration de la webapp est affiché pour tous les rôles, mais la route de
réactivation est bloquée pour TENANT_ADMIN — sans cette garde, un
`expiration_ts` posé par erreur sur je@/af@/svc-tbnotify (dont le compte de
service exécute précisément ce cron) verrouillerait ces comptes sans recours.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

from common import TBClient, setup_logging  # noqa: E402


def process_user(tb: TBClient, u: dict, now_ms: int, log: logging.Logger) -> bool:
    """Traite un user candidat à l'expiration. Retourne True si le compte a
    été réellement désactivé (credentials + attribut deactivated) lors de
    cet appel — False sinon (non échu, non CUSTOMER_USER, déjà traité, ou
    erreur)."""
    uid = u["id"]["id"]
    try:
        attrs = tb.get_server_attrs("USER", uid, ["expiration_ts", "deactivated"])
    except Exception as e:  # noqa: BLE001
        log.warning("attrs %s KO: %s", uid, e)
        return False
    exp = attrs.get("expiration_ts")
    try:
        exp_ts = int(exp) if exp not in (None, "", 0) else 0
    except (TypeError, ValueError):
        return False
    if not exp_ts or exp_ts > now_ms:
        return False  # pas (encore) échu
    if u.get("authority") != "CUSTOMER_USER":
        # Garde anti-lockout (C2) : un expiration_ts posé sur un TENANT_ADMIN
        # (ADMIN_OPS, je@, af@, svc-tbnotify...) ne doit jamais désactiver le
        # compte — la réactivation est bloquée pour ce rôle côté webapp.
        log.warning(
            "expiration_ts échu ignoré pour %s (%s) : authority=%s "
            "(garde anti-lockout, jamais désactivé par cleanup_expired)",
            u.get("email"), uid, u.get("authority"),
        )
        return False
    if attrs.get("deactivated"):
        return False  # déjà désactivé (état réel) — idempotent, pas de ré-appel
    try:
        tb.set_credentials_enabled(uid, False)
        tb.save_server_attrs("USER", uid, {"deactivated": True})
    except Exception as e:  # noqa: BLE001
        log.warning("disable %s KO: %s", uid, e)
        return False
    log.info(
        "Disabled user %s (%s) — expired %s",
        u.get("email"), uid,
        time.strftime("%Y-%m-%d", time.localtime(exp_ts / 1000)),
    )
    return True


def main() -> int:
    log = setup_logging("tb-cleanup-expired")
    now_ms = int(time.time() * 1000)
    tb = TBClient()
    users = tb.list_all_users()
    log.info("Scanning %d users for expired accounts", len(users))
    disabled = sum(1 for u in users if process_user(tb, u, now_ms, log))
    log.info("Done — %d account(s) disabled", disabled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
