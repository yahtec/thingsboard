# Yahtec / TSmart — fast build helper.
#
# Usage :
#   ./build-fast.ps1            -> build rapide (~3 min) : seulement application
#                                  Adapté quand tu ne modifies QUE ui-ngx ou
#                                  l'application Java (cas 90% des itérations
#                                  de thème, navbar, configs).
#   ./build-fast.ps1 -Full      -> build complet (~8 min) : rebuild des modules
#                                  upstream (common/*, dao, rule-engine, etc.)
#                                  + propagation dans le m2 local. À utiliser
#                                  après une modif dans common/* ou dao/.
#
# Le boot JAR est produit à :
#   application/target/thingsboard-<version>-boot.jar
#   (la version est lue dynamiquement depuis pom.xml racine)

param(
    [switch]$Full
)

$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot"
$env:Path      = "C:\dev\maven\apache-maven-3.9.9\bin;$env:Path"
$env:MAVEN_OPTS = "-Xmx2g"

$commonFlags = @(
    '-DskipTests',
    '-Dpkg.skip.deb=true',
    '-Dpkg.skip.rpm=true',
    '-Dpkg.skip.zip=true',
    '-Dlicense.skip=true',
    '-Dcheckstyle.skip=true',
    '-P', 'packaging,skip-deb'
)

$start = Get-Date

if ($Full) {
    Write-Output "==> Full rebuild (recompile common/* + dao + rule-engine + ui-ngx + application)"
    mvn -pl application -am @commonFlags install
} else {
    # On inclut ui-ngx pour que les modifs SCSS / TS / HTML soient prises en compte.
    # ui-ngx est le module Angular qui produit ui-ngx-4.3.1.1.jar (les assets statiques
    # du SPA). Sans lui, le boot jar embarque la version périmée du bundle et tes
    # changements UI ne sont jamais visibles côté navigateur.
    # Coût : ~2-3 min de build Angular en plus du ~30s de l'application.
    Write-Output "==> Fast incremental build (ui-ngx + application, offline mode)"
    mvn -pl ui-ngx,application @commonFlags -o package
}

$dur = (Get-Date) - $start
$tbVersion = ([xml](Get-Content "$PSScriptRoot\pom.xml")).project.version
$boot = "application/target/thingsboard-$tbVersion-boot.jar"
if (Test-Path $boot) {
    $size = [math]::Round((Get-Item $boot).Length / 1MB, 1)
    Write-Output ""
    Write-Output "==> Build OK en $([math]::Round($dur.TotalSeconds, 0))s"
    Write-Output "    Boot JAR : $boot ($size MB)"
} else {
    Write-Output ""
    Write-Output "==> Build ECHOUE (boot jar absent) en $([math]::Round($dur.TotalSeconds, 0))s"
    exit 1
}
