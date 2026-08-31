# tb-dispatcher — provisioning automatique des installations PAC

Copie versionnée de ce qui tourne en prod dans `/home/dump/tb-dispatcher/`.
Jusqu'au 2026-08-28 ce script n'existait **que** sur le serveur, sans historique
ni revue — l'incident de permutation d'automates de Serris a rendu ce trou visible.

## Ce que fait `provision_watcher.py`

Cron **toutes les minutes** (`/etc/cron.d/tb-provision-watcher`) :

```
* * * * * root /usr/bin/python3 /home/dump/tb-dispatcher/provision_watcher.py >> /var/log/tb-provision-watcher.log 2>&1
```

1. lit les `evt_unknown_id` bufferisés sur le device collecteur `heatPumpHybride` ;
2. pour chaque n° de série inconnu, **crée** le device sous le profil `pac hybride`,
   sème le schéma d'attributs de l'unité (`nom_residence`, `adresse`, `photo`…),
   l'assigne au customer `yahtec` ;
3. **rejoue** le payload bufferisé sur le device fraîchement créé, au ts d'origine ;
4. avance le curseur `last_provisioned_evt_ts` (attribut serveur du collecteur).

Idempotent : un device déjà existant est réutilisé, jamais recréé.

> **C'est ce script — et non la rule chain — qui crée les devices.** Le nœud
> `originator -> device(${id})` de la rule chain ne fait que *chercher* une entité
> par nom ; quand il échoue, le message part sur la branche `Failure` →
> `evt_unknown_id` → ce watcher. À retenir avant de chercher un provisioning
> fantôme du côté du moteur de règles.

## Identifiants

Le script lisait `af@yahtec.com` **en dur**. Le dépôt `yahtec/thingsboard` étant
public, les identifiants vivent désormais dans un fichier non versionné :

```
/home/dump/tb-dispatcher/.env      (mode 600, root)
TB_USER=...
TB_PASS=...
```

`_load_dotenv()` le charge au démarrage ; une variable d'environnement déjà
définie a la priorité. Sans identifiants, le script sort en erreur explicite au
lieu de tourner à vide.

⚠ Le compte reste `af@yahtec.com`, un compte **humain**. tb-notify a été basculé
sur le compte de service `svc-tbnotify@yahtec.com` pour cette raison ; ce watcher
a été oublié lors de la bascule. Migration à faire.

## Déploiement

```bash
scp scripts/tb/dispatcher/provision_watcher.py root@10.77.0.74:/home/dump/tb-dispatcher/
ssh root@10.77.0.74 'chmod 750 /home/dump/tb-dispatcher/provision_watcher.py \
  && python3 -m py_compile /home/dump/tb-dispatcher/provision_watcher.py \
  && python3 /home/dump/tb-dispatcher/provision_watcher.py'
```

Le dernier appel est un tick manuel : il doit afficher `watcher tick` puis
`no new unknown events`. Vérifier ensuite l'égalité des empreintes :

```bash
sha256sum scripts/tb/dispatcher/provision_watcher.py
ssh root@10.77.0.74 'sha256sum /home/dump/tb-dispatcher/provision_watcher.py'
```

## Garde-fou `strip()` (2026-08-28)

Un automate a émis `id = "2610000001\r\n"` : le retour-chariot a traversé la rule
chain, le device n'a pas été trouvé, et ce watcher a créé un **6ᵉ device fantôme**
nommé `2610000001\r\n` qui a capté 56 lignes de télémétrie.

Deux couches posées :

| Couche | Où | Quoi |
|---|---|---|
| amont (principale) | rule chain, nœud `extract id -> metadata` | `String(msg.id).trim()` — voir `../rule-chain-pac-hybride-router/add-serial-trim.py` |
| ici (seconde ligne) | `provision_watcher.py` | `str(data.get("id")).strip()` |

Le trim amont suffit dans le cas nominal : l'id nettoyé résout vers le device
existant, la donnée arrive directement au bon endroit et le watcher n'est même
pas sollicité. Le `strip()` d'ici couvre ce qui atteindrait le buffer autrement.

## Reste à faire

- **Clôture de l'alarme `UnknownInstallation`.** La rule chain ne contient aucun
  nœud `clear alarm` : une fois levée, l'alarme reste `MAJOR` à vie. Pire,
  `TbCreateAlarmNode` ne recrée pas une alarme déjà active — il écrase ses
  `details` et laisse `created_time` figé à la première occurrence. Une alarme
  ouverte depuis le 2026-06-01 a ainsi avalé silencieusement l'incident du 28/08.
  Le bon propriétaire de la clôture est **ce watcher** : c'est lui qui résout la
  condition. Un nœud `clear alarm` dans la rule chain ne marche pas — à cet
  endroit `change originator` a déjà basculé l'originator sur le device PAC,
  alors que l'alarme vit sur le collecteur.
- Migration vers `svc-tbnotify@yahtec.com` (cf. ci-dessus).
- Pas de tests : le script n'a aucune couverture. À faire si on y retouche.
