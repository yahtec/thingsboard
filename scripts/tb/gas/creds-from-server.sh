#!/usr/bin/env bash
# A SOURCER, jamais execute directement : exporte TB_USER et TB_PASS dans le shell
# courant, lus via SSH depuis /home/dump/tb-notify/.env sur l'hote de prod. Ce fichier
# (mode 600, root) contient les identifiants du compte de service
# svc-tbnotify@yahtec.com (TENANT_ADMIN), deja utilise par tb-notify.
#
# Objectif : token_or_login() (scripts/tb/widgets/_wt_patch.py,
# scripts/tb/dashboards/_lib_tb.py) accepte TB_USER+TB_PASS depuis l'environnement en
# dernier recours (apres TB_TOKEN et --pwd) -- ce script les y depose SANS jamais
# afficher le mot de passe ni l'ecrire dans un fichier local. Seul le nom
# d'utilisateur est confirme par un echo.
#
# Usage (depuis Git Bash / le shell POSIX de ce projet) :
#   source scripts/tb/gas/creds-from-server.sh
#   python patch-fault-diagnostic-leak-line.py --dry-run
#
# Ne stocke rien sur disque : les variables ne vivent que dans l'environnement du
# shell qui a source ce fichier, et disparaissent a sa fermeture.

# Detection source-vs-execute (le trick `return` : ne reussit que si ce fichier est
# source). Executer ce script par erreur ne doit jamais faire echouer silencieusement
# ni, pire, imprimer quoi que ce soit d'utile a un attaquant -- juste un rappel clair.
if ! (return 0 2>/dev/null); then
    echo "creds-from-server.sh doit etre SOURCE, pas execute : 'source ${BASH_SOURCE[0]:-$0}'" >&2
    exit 1
fi

_creds_host="root@10.77.0.74"
_creds_key="${USERPROFILE:-$HOME}/.ssh/yahtec-ota"
_creds_env_file="/home/dump/tb-notify/.env"

_creds_raw="$(ssh -i "$_creds_key" -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o LogLevel=ERROR "$_creds_host" \
    "grep -E '^(TB_USER|TB_PASS)=' '$_creds_env_file'" 2>/dev/null)"
_creds_status=$?

if [ $_creds_status -ne 0 ] || [ -z "$_creds_raw" ]; then
    echo "creds-from-server.sh: lecture de $_creds_env_file sur $_creds_host a echoue" >&2
    unset _creds_raw _creds_status _creds_host _creds_key _creds_env_file
    return 1
fi

unset TB_USER TB_PASS
while IFS='=' read -r _creds_k _creds_v; do
    # Retire des guillemets englobants eventuels (KEY="valeur" ou KEY='valeur') :
    # forme parfois utilisee dans les .env, jamais garantie mais inoffensive a nettoyer.
    case "$_creds_v" in
        \"*\") _creds_v="${_creds_v#\"}"; _creds_v="${_creds_v%\"}" ;;
        \'*\') _creds_v="${_creds_v#\'}"; _creds_v="${_creds_v%\'}" ;;
    esac
    case "$_creds_k" in
        TB_USER) export TB_USER="$_creds_v" ;;
        TB_PASS) export TB_PASS="$_creds_v" ;;
    esac
done <<< "$_creds_raw"

unset _creds_raw _creds_status _creds_host _creds_key _creds_env_file _creds_k _creds_v

if [ -z "$TB_USER" ] || [ -z "$TB_PASS" ]; then
    echo "creds-from-server.sh: TB_USER ou TB_PASS absent/vide dans le .env distant" >&2
    unset TB_USER TB_PASS
    return 1
fi

# Confirmation limitee au nom d'utilisateur -- TB_PASS n'est JAMAIS affiche.
echo "creds-from-server.sh: TB_USER=$TB_USER importe depuis le serveur (TB_PASS non affiche)"
