# Registres capteurs gaz — outillage dashboard

Spec : `docs/superpowers/specs/2026-07-31-registres-capteurs-gaz-dashboard-design.md`
Plan : `docs/superpowers/plans/2026-07-31-registres-capteurs-gaz-dashboard.md`

## Principe

`_src/gas_lib.js` est la **source unique** de la logique d'affichage gaz (decodage du
champ de bits, format de version, garde R7, decoupage en segments, fabrication des
lignes, et fenetre d'alarme capteur `leakWindow`). Elle est injectee telle quelle dans
trois widget_types. Ne jamais la recopier a la main dans un widget : modifier ce
fichier puis rejouer les scripts.

**Amendement du 2026-08-24** : le widget timeline des registres (`tsmart.gas_registers`,
quatorze pistes) a ete retire de la production et remplace par une ligne calculee
« alarme capteur » dans le widget Diagnostic defaut -- voir l'amendement en fin du plan.
A 1 echantillon/minute l'excursion de concentration lors d'un defaut gaz est invisible ;
seul le bit d'alarme, maintenu 5 minutes par le capteur, est observable.

## Prerequis

```
set TB_TOKEN=<jwt frais>        # ou --pwd sur chaque script
```

## Ordre d'execution

```
python patch-gas-state-rows.py --dry-run              && python patch-gas-state-rows.py
python patch-fault-diagnostic-gas-registers.py --dry-run && python patch-fault-diagnostic-gas-registers.py
python patch-fault-diagnostic-leak-line.py --dry-run   && python patch-fault-diagnostic-leak-line.py
python add-gas-threshold-series.py --dry-run          && python add-gas-threshold-series.py
python retire-gas-registers-widget.py --dry-run       && python retire-gas-registers-widget.py
```

Tous les scripts sont idempotents : rejouables sans effet de bord.

## Tests

```
python -m pytest tests/ -v
"c:/Projets/TB/thingsboard/ui-ngx/target/node/node.exe" _src/gas_lib.test.js
```

Les tests d'ancres comparent aux sources live capturees dans `tests/fixtures/`. Si l'un
echoue, la source live a change : recapturer la fixture et corriger la constante
d'ancre — jamais assouplir le test.

## Installations de reference

- **2602000002** (relEsp 1.1.8 / relStm 1.4.6) : registres renseignes, cas complet.
- **2602000001** (relEsp 1.1.4 / relStm 1.4.4) : registres presents mais a 0, cas R7.
