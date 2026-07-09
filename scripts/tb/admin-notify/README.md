# tb-notify

Notifications mail pour les défauts des chaufferies TDUO sur ThingsBoard yahtec.

- **`fault_notify.py`** — cron 1/min, mail aux gestionnaires d'une chaufferie quand un nouveau défaut apparaît (coalesce 60 s pour grouper les rafales).
- **`fault_digest.py`** — cron toutes les 4 h, mail récap aux admins du parc s'il y a au moins un défaut actif.
- **`webapp.py`** — appli de gestion des comptes intervenants (`https://thingsboard.tsmart.fr/admin-notify/`) : invitation, édition (droits, chaufferies visibles), désactivation non-destructive. Les chaufferies cochées par compte sont réconciliées vers des relations RBAC **CanView** (party-customer → site-customer) — plus aucune liste d'emails n'est écrite en attribut.

Source de vérité : télémétrie `evt_*` sur les devices `pac hybride` (mêmes mappings et même logique de pairing que le widget historique du dashboard).

---

## Installation

### 1. Compte SMTP Brevo

1. Crée un compte sur https://www.brevo.com (gratuit, 300 mails/jour)
2. Profil → **SMTP & API** → onglet **SMTP** → **Generate a new SMTP key**
3. Note : `Login` (= ton email Brevo) + la clé SMTP générée
4. Ajoute un **expéditeur vérifié** (ou vérifie le domaine `yahtec.com`) — c'est l'adresse `SMTP_FROM`.
   - Tant que le domaine n'est pas vérifié, tu peux utiliser une adresse perso vérifiée comme expéditeur.

### 2. Fichier `.env`

```bash
cd /home/dump/tb-notify
cp .env.example .env
nano .env
```

Renseigne au minimum :
- `SMTP_USER` / `SMTP_PASS` (creds Brevo)
- `SMTP_FROM` (adresse expéditeur vérifiée)
- `WEB_SECRET` : `openssl rand -hex 48`
- `TB_PASS` : mot de passe TB de `af@yahtec.com`

### 3. Bootstrap

```bash
bash setup.sh                                          # crée .venv + installe deps
sudo cp deploy/tb-notify-web.service /etc/systemd/system/
sudo cp deploy/tb-notify.cron /etc/cron.d/tb-notify
sudo cp deploy/tb-notify.logrotate /etc/logrotate.d/tb-notify
sudo systemctl daemon-reload
sudo systemctl enable --now tb-notify-web.service
```

### 4. Nginx

Dans `/etc/nginx/sites-enabled/bootloader.tsmart.fr`, insère le bloc de
`deploy/nginx-snippet.conf` à l'intérieur du `server { … server_name thingsboard.tsmart.fr; … }`,
**avant** le `location /` catch-all (sinon il sera shadowé). Puis :

```bash
sudo nginx -t && sudo systemctl reload nginx
```

⚠️ Rappel : `sites-enabled/bootloader.tsmart.fr` est un fichier régulier sur ce serveur, pas un symlink — édite-le directement.

### 5. Premier passage

1. Ouvrir https://thingsboard.tsmart.fr/admin-notify/
2. Se connecter avec un compte tenant admin yahtec (ou `ADMIN_OPS`)
3. Inviter un intervenant (`/invite`) ou éditer un compte existant (`/accounts/{uid}/edit`) : cocher les chaufferies visibles (réconciliées en relations CanView) et/ou le droit admin
4. Enregistrer

### 6. Tests à la main

```bash
cd /home/dump/tb-notify
.venv/bin/python fault_notify.py        # log "no recipients" par device tant qu'aucun CanView n'est configuré
.venv/bin/python fault_digest.py        # envoie le récap si défauts actifs
```

Logs : `/var/log/tb-notify.log` (logique métier), `/var/log/tb-notify-cron.log` (sortie cron), `/var/log/tb-notify-web.log` (uvicorn).

---

## Comment ça marche

### Notification immédiate (gestionnaires)

Curseur par device : attribut serveur `last_notified_evt_ts` (epoch ms).
À chaque cron :
1. Lit `evt_*` entre `cursor` et `now − 60 s` (le buffer 60 s permet de grouper les rafales d'apparition multiples).
2. Reproduit le pairing du widget : dédup 12 s + appariement apparition/résolution + résolutions inverse-paired.
3. Garde uniquement les `evt_type == 1` apparus dans la fenêtre.
4. Envoie 1 mail HTML par chaufferie listant tous les défauts apparus, aux destinataires calculés par `get_recipients_for_device()` (voir « Routage des destinataires » ci-dessous) — plus aucune liste d'emails n'est lue depuis un attribut `gestionnaires`.
5. Avance le curseur uniquement si succès (sinon retry au prochain cron).

### Routage des destinataires (RBAC CanView)

Le routage des mails de défaut (notification immédiate) ne repose plus sur un attribut USER `chaufferies` (retiré) : il dérive dynamiquement les device-ids visibles par un intervenant de ses relations **CanView** (party-customer → site-customer). Concrètement, pour chaque device, `get_recipients_for_device()` retient les `CUSTOMER_USER` non-admin dont le party-customer a une relation CanView vers le site-customer propriétaire de ce device ; `webapp.py` réconcilie ces relations (`_sync_canview`) à chaque enregistrement d'un compte, à partir des chaufferies cochées dans le formulaire.

Deux gardes s'appliquent en plus de ce calcul :
- Un attribut USER `deactivated=true` (posé par la désactivation non-destructive d'un compte, cf. `webapp.py` / chantier RBAC) exclut l'intervenant de tout routage mail (immédiat et digest), quelles que soient ses relations CanView.
- L'ancienne garde sur `additionalInfo.userCredentialsEnabled` a été **retirée** (chantier #5, A1) : TB positionne ce flag à `false` à la création du compte et ne le corrige qu'au premier login, ce qui excluait à tort un intervenant activé mais jamais encore connecté. `deactivated` est désormais la seule garde d'exclusion applicative.

### Digest 4 h (admins parc)

À chaque cron :
1. Pour chaque device pac hybride : lit `evt_*` sur 30 derniers jours, reproduit le pairing.
2. Garde les défauts ouverts (apparus, jamais résolus).
3. Si zéro défaut sur tout le parc → silence (aucun mail envoyé).
4. Sinon : 1 mail HTML aux destinataires de `parc_admins` (attribut serveur sur le customer yahtec) listant chaque chaufferie + ses défauts en cours + heure d'apparition.

### Pourquoi pas TB Notification Center

- Notification Center notifie 1 alarme = 1 mail, pas de digest agrégé.
- Les alarmes profile (`HPxFault`, `BoilxFault`…) restent parfois orphelines, donc pas fiables comme état "défaut en cours". `evt_*` reste la source de vérité.
- Templating HTML riche (tableau de défauts) impossible en rule chain.

---

## Schéma d'attributs

| Entité | Attribut / Relation | Type | Usage |
|---|---|---|---|
| `DEVICE` (pac hybride) | `last_notified_evt_ts` | `long` | Curseur géré par `fault_notify.py`. |
| `DEVICE` (pac hybride) | `address` / `label` | `string` | Affichage humain (déjà utilisé par les widgets). |
| `DEVICE` (pac hybride) | `site_customer_id` | `string` (uuid) | Site-customer propriétaire du device ; base de la dérivation CanView → device-ids. |
| `CUSTOMER` (party) → `CUSTOMER` (site) | relation `CanView` (typeGroup `COMMON`) | — | Source de vérité du routage par-device. Remplace l'ancien attribut USER `chaufferies` (retiré). Réconciliée par `webapp.py` (`_sync_canview`). |
| `USER` | `is_admin` | `bool` | Compte inclus dans `get_admin_emails()` (digest 4 h) et exclu du routage par-device. |
| `USER` | `deactivated` | `bool` | Posé par la désactivation non-destructive (`webapp.py`) ; exclut l'utilisateur de tout routage mail. |
| `CUSTOMER` (yahtec) | `parc_admins` | `[email]` ou `csv` | Recipients du digest 4 h (fallback historique, hors-scope de ce changement). |

## Tests

```bash
cd scripts/tb/admin-notify
python -m pytest tests/          # offline, aucun appel réseau/TB — vérifie le routage CanView
```
