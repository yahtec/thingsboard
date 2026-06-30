# tb-notify

Notifications mail pour les défauts des chaufferies TDUO sur ThingsBoard yahtec.

- **`fault_notify.py`** — cron 1/min, mail aux gestionnaires d'une chaufferie quand un nouveau défaut apparaît (coalesce 60 s pour grouper les rafales).
- **`fault_digest.py`** — cron toutes les 4 h, mail récap aux admins du parc s'il y a au moins un défaut actif.
- **`webapp.py`** — petit formulaire web (`https://thingsboard.tsmart.fr/admin-notify/`) pour gérer les emails gestionnaires par chaufferie + la liste des admins du parc.

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
2. Se connecter avec un compte tenant admin yahtec
3. Renseigner les emails gestionnaires par chaufferie + la liste des admins du parc
4. Enregistrer

### 6. Tests à la main

```bash
cd /home/dump/tb-notify
.venv/bin/python fault_notify.py        # devrait dire "no gestionnaires" tant que vide
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
4. Envoie 1 mail HTML par chaufferie listant tous les défauts apparus, aux emails de l'attribut `gestionnaires` (JSON `[{name, email}]`).
5. Avance le curseur uniquement si succès (sinon retry au prochain cron).

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

| Entité | Attribut | Type | Usage |
|---|---|---|---|
| `DEVICE` (pac hybride) | `gestionnaires` | `[{name, email}]` | Recipients notif immédiate. Édité via webapp. |
| `DEVICE` (pac hybride) | `last_notified_evt_ts` | `long` | Curseur géré par `fault_notify.py`. |
| `DEVICE` (pac hybride) | `address` / `label` | `string` | Affichage humain (déjà utilisé par les widgets). |
| `CUSTOMER` (yahtec) | `parc_admins` | `[email]` ou `csv` | Recipients du digest 4 h. Édité via webapp. |
