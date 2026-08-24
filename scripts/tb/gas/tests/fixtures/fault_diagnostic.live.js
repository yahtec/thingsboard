var FAULT_LABELS = {0:'',1:'Defaut sonde depart',2:'Defaut sonde retour',3:'Defaut sonde fumee',4:'Defaut sonde pression',5:'Defaut debit eau',6:'Defaut surpression eau',7:'Surchauffe',8:'Defaut bruleur',9:'Defaut ventil. bruleur',10:'Defaut preventilation',11:'Defaut delta temp.',12:'Defaut temp. fumee',13:'Defaut circuit fumee',14:'Bruleur non linearise',15:'Defaut communication',16:'Defaut sous-tension',17:'Defaut surtension',18:'Manque phase',19:'Marche a sec',20:'Pression trop forte',21:'Pression trop faible',22:'Moteur trop chaud',23:'Defaut moteur',24:'Pompe bloquee',25:'Surchauffe module',26:'Avertissement module',27:'Defaut module',28:'Defaut capteur',29:'Defaut communication',30:'Defaut vanne eau',31:'Utilisation excessive',32:'Adaptation plage',33:'Surcharge mecanique',34:'Defaut securite',35:'Erreur test clapet',36:'Temperature trop elevee',37:'Fumee detectee',38:'Defaut communication',39:'Defaut communication',40:'Defaut communication',41:'Pression trop faible',42:'Redemarrage regulateur',43:'Manipulation tactile',44:'Filtre encrasse',45:'Defaut carte 1',46:'Defaut carte 2',47:'Defaut carte 3',48:'Defaut carte 4',49:'Defaut carte 5',50:'Defaut carte 6',51:'Defaut carte 7',52:'Defaut bruleur 8',53:'Defaut bruleur 9',54:'Defaut bruleur 10',55:'Defaut bruleur 11',56:'Defaut bruleur 12',57:'Defaut bruleur 13',58:'Defaut interne boitier',59:'Defaut general boitier',60:'Nb max reset atteint',61:'Defaut pompe ECS',62:'Defaut module FTP',63:'Defaut pression fumee',70:'Defaut sonde T entree chaud.',71:'Defaut sonde T sortie chaud.',72:'Defaut sonde T fumee chaud.',73:'Defaut sonde T entree PAC',74:'Defaut sonde T BP',75:'Defaut sonde T HP-h',76:'Defaut sonde T HP-c',77:'Defaut sonde T air ext.',78:'Defaut pression air',79:'Defaut pression eau',80:'Defaut pression HP',81:'Defaut pression BP',82:'Gaz detecte',83:'Defaut surchauffe chaud.',84:'Defaut com. pompe',85:'Defaut com. compresseur',86:'Defaut com. gaz G20',87:'Defaut com. gaz R290',88:'Defaut communication',89:'Defaut pression eau',90:'Defaut HP max',91:'Defaut BP min',92:'Defaut variateur 0Hz',93:'Defaut variateur',94:'Defaut surchauffe PAC',95:'Defaut T sortie PAC',96:'Defaut T entree PAC',97:'Defaut T BP',98:'Defaut T HP chaud',99:'Defaut T HP froid',100:'Defaut pression eau bas',101:'Defaut pression eau haut',102:'Defaut pression air',103:'Defaut vitesse ventilateur',104:'Defaut sonde T entree module',105:'Defaut sonde T exterieure',106:'Defaut sonde T sortie ECS',107:'Defaut sonde T entree ECS',108:'Defaut sonde T sortie chauffage',109:'Defaut sonde T entree chauffage',110:'Defaut sonde T stockage',111:'Gaz R290 détecté',112:'Gaz G20 détecté',113:'Defaut temperature sortie chaudiere'};

// Métadonnées clés snapshot : libellé (texte écran), unité affichée, échelle raw→display, décimales.
// Source : spec utilisateur 2026-05-06 (colonnes "texte écran" + "unité").
var KEY_META = {
    // __GAZ_SNAPSHOT_PATCH__ : gaz / securite (snapshot firmware 2026-07-08), libelles ASCII
    gas_r290_conc:{l:'Concentration R290',u:'%LFL',s:0.1,d:1},
    gas_g20_conc :{l:'Concentration G20', u:'%LFL',s:0.1,d:1},
    gas_r290_err :{l:'Defaut capteur R290 (registre)',u:'',s:1,d:0},
    gas_g20_err  :{l:'Defaut capteur G20 (registre)', u:'',s:1,d:0},
    // Inputs
    v:{l:'Tension alimentation 24V',u:'V',s:0.1,d:1},
    r_b1:{l:'Read bit states brûleur registre 1',u:'',s:1,d:0},
    r_b2:{l:'Read bit states brûleur registre 2',u:'',s:1,d:0},
    r_b3:{l:'Read bit states brûleur registre 3',u:'',s:1,d:0},
    t_ib:{l:'T In Chaudière / T out PAC',u:'°C',s:0.1,d:1},
    t_ob:{l:'T out Chaudière',u:'°C',s:0.1,d:1},
    t_sb:{l:'T fumées',u:'°C',s:0.1,d:1},
    t_ip:{l:'T In PAC',u:'°C',s:0.1,d:1},
    t_bp:{l:'T BP',u:'°C',s:0.1,d:1},
    t_hph:{l:'T HP chaud',u:'°C',s:0.1,d:1},
    t_hpc:{l:'T HP froid',u:'°C',s:0.1,d:1},
    t_e:{l:'T extérieure',u:'°C',s:0.1,d:1},
    t_cond:{l:'T condensation',u:'°C',s:0.1,d:1},
    t_evap:{l:'T evaporation',u:'°C',s:0.1,d:1},
    t_oh:{l:'T surchauffe',u:'°C',s:0.1,d:1},
    t_sc:{l:'T sous-refroidissement',u:'°C',s:0.1,d:1},
    wf_b:{l:'Débit eau',u:'L/h',s:1,d:0},
    w_ecs:{l:'Flag/valeur ECS',u:'',s:1,d:0},
    b_fan:{l:'Vitesse brûleur',u:'rpm',s:1,d:0},
    wp_b:{l:'Pression eau',u:'bar',s:0.1,d:1},
    ap:{l:'Pression Air',u:'Pa',s:1,d:0},
    f_ap:{l:'Pression air',u:'',s:1,d:0},
    p_fan:{l:'Vitesse fan',u:'rpm',s:1,d:0},
    p_hp:{l:'Pression HP',u:'bar',s:0.1,d:1},
    p_bp:{l:'Pression BP',u:'bar',s:0.1,d:1},
    pos_ev:{l:'position détendeur',u:'',s:1,d:0},
    pb_dp:{l:'Delta P pompe',u:'mCE',s:0.1,d:1},
    pb_wf:{l:'Débit pompe',u:'m³/h',s:0.1,d:2},
    pb_e:{l:'Energie pompe',u:'kWh',s:1,d:0},
    pb_pw:{l:'Puissance pompe',u:'W',s:1,d:0},
    pb_ot:{l:'Temps ON pompe',u:'h',s:1,d:0},
    pb_spd:{l:'Vitesse pompe',u:'%',s:1,d:0},
    pb_om:{l:'mode pompe',u:'',s:1,d:0},
    pe_dp:{l:'Pump ECS — Différentiel pression',u:'',s:1,d:0},
    pe_wf:{l:'Pump ECS — Débit',u:'',s:1,d:0},
    pe_e:{l:'Pump ECS — Énergie',u:'',s:1,d:0},
    pe_pw:{l:'Pump ECS — Puissance',u:'',s:1,d:0},
    pe_ot:{l:'Pump ECS — Temps fonctionnement',u:'',s:1,d:0},
    pe_spd:{l:'Pump ECS — Vitesse',u:'',s:1,d:0},
    pe_om:{l:'Pump ECS — Operation Mode',u:'',s:1,d:0},
    pl_dp:{l:'Pump Loop — Différentiel pression',u:'',s:1,d:0},
    pl_wf:{l:'Pump Loop — Débit',u:'',s:1,d:0},
    pl_e:{l:'Pump Loop — Énergie',u:'',s:1,d:0},
    pl_pw:{l:'Pump Loop — Puissance',u:'',s:1,d:0},
    pl_ot:{l:'Pump Loop — Temps fonctionnement',u:'',s:1,d:0},
    pl_spd:{l:'Pump Loop — Vitesse',u:'',s:1,d:0},
    pl_om:{l:'Pump Loop — Operation Mode',u:'',s:1,d:0},
    c_s:{l:'Status variateur',u:'',s:1,d:0},
    c_of:{l:'Fréquence sortie compresseur',u:'Hz',s:0.1,d:1},
    c_ov:{l:'Tension sortie compresseur',u:'V',s:1,d:0},
    c_oc:{l:'Courant sortie compresseur',u:'A',s:0.1,d:1},
    c_op:{l:'Puissance sortie compresseur',u:'W',s:1,d:0},
    c_iv:{l:'Tension entrée compresseur',u:'V',s:1,d:0},
    c_ic:{l:'Courant entrée compresseur',u:'A',s:0.1,d:1},
    c_ip:{l:'Puissance entrée compresseur',u:'W',s:1,d:0},
    t_ipm:{l:'T° IPM variateur',u:'°C',s:1,d:0},
    t_pfc:{l:'T° PFC variateur',u:'°C',s:1,d:0},
    t_pcp:{l:'T° PCB variateur',u:'°C',s:1,d:0},
    c_fc0:{l:'Registre 0 variateur',u:'',s:1,d:0},
    c_fc1:{l:'Registre 1 variateur',u:'',s:1,d:0},
    c_fc2:{l:'Registre 2 variateur',u:'',s:1,d:0},
    flt:{l:'Fault générique',u:'',s:1,d:0},
    p_s:{l:'PAC Status',u:'',s:1,d:0},
    b_s:{l:'Boiler Status',u:'',s:1,d:0},
    s_use:{l:"Status mode d'usage",u:'',s:1,d:0},
    p_fs:{l:'PAC Fault State',u:'',s:1,d:0},
    c_if:{l:'Inverter Internal Fault',u:'',s:1,d:0},
    p_acc:{l:'PAC anti-court-cycle',u:'',s:1,d:0},
    // Outputs
    bm:{l:'Boiler Mode',u:'',s:1,d:0},
    w_bs1:{l:'Write Boiler State 1',u:'',s:1,d:0},
    w_bs2:{l:'Write Boiler State 2',u:'',s:1,d:0},
    req_boiler_pwr:{l:'Consigne puissance brûleur',u:'%',s:1,d:0},
    req_inv_dir:{l:'Consigne direction freq variateur',u:'',s:1,d:0},
    req_t_out:{l:'Consigne T° sortie',u:'°C',s:1,d:0},
    req_wf:{l:'Consigne débit',u:'L/h',s:1,d:0},
    dt_d:{l:'Date — jour',u:'',s:1,d:0},
    dt_m:{l:'Date — mois',u:'',s:1,d:0},
    dt_y:{l:'Date — année',u:'',s:1,d:0},
    tm_h:{l:'Heure',u:'',s:1,d:0},
    tm_m:{l:'Minute',u:'',s:1,d:0},
    tm_s:{l:'Seconde',u:'',s:1,d:0},
    b_spd_min:{l:'Vitesse brûleur min',u:'rpm',s:1,d:0},
    b_spd_max:{l:'Vitesse brûleur max',u:'rpm',s:1,d:0},
    b_spd_prevent:{l:'Vitesse brûleur préventilation',u:'rpm',s:1,d:0},
    oh_rgl:{l:'Régulation surchauffe',u:'°C',s:1,d:0},
    oh_tm_l:{l:'Timer surchauffe low',u:'s',s:1,d:0},
    oh_tm_h:{l:'Timer surchauffe high',u:'s',s:1,d:0},
    t_max_out:{l:'T° sortie max autorisée',u:'°C',s:1,d:0},
    coef_waterflow:{l:'Coefficient Débit',u:'',s:1,d:0},
    p_water_max:{l:'Pression eau max',u:'bar',s:0.1,d:1},
    t_glycol:{l:'Taux glycol',u:'',s:1,d:0},
    pwr_max:{l:'Puissance max',u:'kW',s:1,d:0},
    m_dpf_pos:{l:'Position manuel cible détendeur',u:'',s:1,d:0},
    transmit_host_last_10s:{l:'Flag transmission host 120s',u:'',s:1,d:0},
    max_fan_speed:{l:'Vitesse max fan',u:'%',s:1,d:0},
    start_step_pac_heat:{l:'pos. init détendeur chaud',u:'',s:1,d:0},
    start_step_pac_cool:{l:'pos. init détendeur froid',u:'',s:1,d:0},
    pac_fault1:{l:'PAC fault code 1',u:'',s:1,d:0},
    pac_fault2:{l:'PAC fault code 2',u:'',s:1,d:0},
    pac_fault3:{l:'PAC fault code 3',u:'',s:1,d:0},
    boiler_fault1:{l:'Boiler fault code 1',u:'',s:1,d:0},
    stm_v_maj:{l:'Firmware STM32 major',u:'',s:1,d:0},
    stm_v_min:{l:'Firmware STM32 minor',u:'',s:1,d:0},
    stm_v_build:{l:'Firmware STM32 build',u:'',s:1,d:0},
    screen_v_maj:{l:'Firmware écran major',u:'',s:1,d:0},
    screen_v_min:{l:'Firmware écran minor',u:'',s:1,d:0},
    screen_v_build:{l:'Firmware écran build',u:'',s:1,d:0},
    esp_time:{l:'Timestamp ESP epoch ms',u:'',s:1,d:0},
    id_pac:{l:'Index PAC',u:'',s:1,d:0},
    reverse_v4v:{l:'V4V inversée',u:'',s:1,d:0},
    be_active:{l:'Burner Electronic actif',u:'',s:1,d:0},
    be_mode:{l:'BE mode',u:'',s:1,d:0},
    be_mode_c:{l:'BE mode confirmé',u:'',s:1,d:0},
    b_force_h:{l:'Forçage brûleur haut régime',u:'',s:1,d:0},
    b_force_l:{l:'Forçage brûleur bas régime',u:'',s:1,d:0},
    b_force_full:{l:'Forçage brûleur plein régime',u:'',s:1,d:0},
    be_test_progress:{l:'BE test progression',u:'%',s:1,d:0},
    be_test_time:{l:'BE test durée',u:'s',s:1,d:0},
    o2:{l:'Analyse O2 combustion',u:'',s:1,d:1},
    co:{l:'Analyse CO combustion',u:'',s:1,d:0},
    nox:{l:'Analyse NOx combustion',u:'',s:1,d:0},
    screen_ota_request:{l:'Demande OTA écran',u:'',s:1,d:0}
};

// Remplacement numérique → texte (col "remplacement numérique par texte" du spec)
var ENUM_LABELS = {
    gas_r290_err:{0:'OK'},
    gas_g20_err :{0:'OK'},
    p_s: {0:'off',1:'init',2:'init',3:'init',4:'marche',5:'fault',6:'fault gaz',7:'anti-cycle',8:'stop in progress',9:'dégivrage',10:'pump down'},
    b_s: {0:'off',1:'start',2:'start',3:'start',4:'start',5:'flamme',6:'attente redémarrage',7:'arrêt température',8:'défaut',9:'nouveau cycle',10:'maintenance'},
    s_use: {0:'off',1:'pac seul',2:'chaudière seul',3:'pac + chaudière'},
    req_inv_dir: {'-1':'baisse fréquence',0:'pas de modif',1:'augmentation'},
    coef_waterflow: {110:'DN15',224:'DN20',448:'DN25'},
    pb_om: {1:'vitesse fixe',3:'delta P constant',4:'delta P variable'}
};

var KEY_GROUPS = [
    {title:'Pressions',     keys:['p_bp','p_hp','p_acc','p_water_max','wp_b','ap']},
    {title:'Températures',  keys:['t_bp','t_hph','t_hpc','t_evap','t_cond','t_sc','t_oh','t_e','t_ib','t_ob','t_ip','t_ipm','t_pcp','t_pfc','t_sb','t_max_out','t_glycol']},
    {title:'Compresseur / Variateur', keys:['c_ip','c_iv','c_op','c_ov','c_ic','c_oc','c_if','c_of','c_s','c_fc0','c_fc1','c_fc2']},
    {title:'Pompes',        keys:['pb_pw','pb_spd','pb_wf','pb_dp','pb_e','pb_om','pb_ot','pe_pw','pe_spd','pe_wf','pe_dp','pe_e','pe_om','pe_ot','pl_pw','pl_spd','pl_wf','pl_dp','pl_e','pl_om','pl_ot']},
    {title:'Brûleur / Chaudière', keys:['b_s','bm','b_fan','b_spd_min','b_spd_max','b_spd_prevent','b_force_full','b_force_h','b_force_l','boiler_fault1','pac_fault1','pac_fault2','pac_fault3','flt']},
    {title:'Consignes / Commande', keys:['req_boiler_pwr','req_t_out','req_wf','req_inv_dir','pos_ev','reverse_v4v','pwr_max','r_b1','r_b2','r_b3']},
    {title:'Combustion',    keys:['co','o2','nox','f_ap','m_dpf_pos','max_fan_speed']},
    {title:'Auxiliaires',   keys:['p_fan','p_fs','p_s','v','w_bs1','w_bs2','w_ecs','wf_b','coef_waterflow','s_use','tm_h','tm_m']}
];

// Pour chaque code défaut, clés à mettre dans le bandeau KPI (la première est highlightée)
var FAULT_KPI = {
    81:['p_bp','t_bp'], 91:['p_bp','t_bp'], 92:['p_bp','t_bp'],   // BP
    80:['p_hp','t_hph','t_hpc'], 90:['p_hp','t_hph'], 98:['t_hph'], 99:['t_hpc'],
    78:['ap','p_fan'], 102:['ap'], 103:['p_fan','max_fan_speed'],
    79:['wp_b','p_water_max'], 89:['wp_b'], 100:['wp_b'], 101:['wp_b'],
    94:['t_evap','t_cond','t_sc','t_oh'], 95:['t_ob','req_t_out'], 96:['t_ib'], 97:['t_bp'],
    93:['c_if','c_of','c_iv','c_ov'], 85:['c_if','c_of','c_iv','c_ov'],
    5:['wf_b','pb_wf','pb_pw'], 7:['t_ob','t_ib'], 83:['t_ob','t_ib','b_s']
};

// Tableaux de valeurs au moment du défaut, regroupés par section.
// Sélection : colonne "afficher tableau = oui" du spec utilisateur.
var SECTION_TABLES = {
    'PAC': [
        {title:'PAC', keys:[
            'p_s','p_hp','p_bp','ap','p_fan','pos_ev',
            't_e','t_ip','t_bp','t_hph','t_hpc','t_cond','t_evap','t_oh','t_sc',
            'flt'
        ]},
        {title:'Compresseur', keys:[
            'c_s','c_of','c_op','c_ip','c_oc','c_ic','c_ov','c_iv',
            'c_fc0','c_fc1','c_fc2'
        ]},
        {title:'Gaz / Securite', keys:[
            'gas_r290_conc','gas_g20_conc','gas_r290_err','gas_g20_err'
        ]},
        {title:'Codes defaut (bruts)', keys:[ /* __FAULTCODES_SNAPSHOT_PATCH__ */
            'pac_fault1','pac_fault2','pac_fault3','boiler_fault1'
        ]}
    ],
    'Chaudière': [
        {title:'Chaudière', keys:[
            'b_s','t_ib','t_ob','t_sb','t_e','wf_b','wp_b','b_fan'
        ]},
        {title:'Pompe chaudière', keys:[
            'pb_dp','pb_wf','pb_e','pb_pw','pb_spd','pb_om'
        ]}
    ]
};

var CHART_COLORS = ['#c62828','#1565c0','#2e7d32','#e65100','#6a1b9a','#00838f','#4e342e','#37474f','#880e4f','#0d47a1'];

// Définition des graphes (1 graphe normalisé multi-signaux par groupe).
// Sélection : colonne "afficher courbes = oui" du spec utilisateur.
var SNAP_PAC_CHART = {
    title:'PAC', h:360,
    series:[
        {key:'p_hp',  label:'Pression HP',     unit:'bar', d:1, color:'#c62828', yMin:0,   yMax:50},
        {key:'p_bp',  label:'Pression BP',     unit:'bar', d:1, color:'#1565c0', yMin:0,   yMax:50},
        {key:'ap',    label:'Pression Air',    unit:'Pa',  d:0, color:'#5d4037', yMin:0,   yMax:300},
        {key:'p_fan', label:'Vitesse fan',     unit:'rpm', d:0, color:'#3949ab', yMin:0,   yMax:2000},
        {key:'pos_ev', label:'Position détendeur', unit:'', d:0, color:'#7e57c2', yMin:0, yMax:2200},
        {key:'t_e',   label:'T extérieure',    unit:'°C', d:1, color:'#9e9d24', yMin:-30, yMax:120},
        {key:'t_ip',  label:'T In PAC',        unit:'°C', d:1, color:'#0d47a1', yMin:-30, yMax:120},
        {key:'t_ib',  label:'T out PAC',       unit:'°C', d:1, color:'#1b5e20', yMin:-30, yMax:120},
        {key:'t_bp',  label:'T BP',            unit:'°C', d:1, color:'#2e7d32', yMin:-30, yMax:120},
        {key:'t_hph', label:'T HP chaud',      unit:'°C', d:1, color:'#e65100', yMin:-30, yMax:120},
        {key:'t_hpc', label:'T HP froid',      unit:'°C', d:1, color:'#6a1b9a', yMin:-30, yMax:120},
        {key:'t_evap',label:'T evaporation',   unit:'°C', d:1, color:'#00838f', yMin:-30, yMax:120},
        {key:'t_cond',label:'T condensation',  unit:'°C', d:1, color:'#4e342e', yMin:-30, yMax:120},
        {key:'t_oh',  label:'T surchauffe',    unit:'°C', d:1, color:'#880e4f', yMin:-30, yMax:120},
        {key:'t_sc',  label:'T sous-refr.',    unit:'°C', d:1, color:'#37474f', yMin:-30, yMax:120},
        {key:'c_of',  label:'Fréq. compr.',    unit:'Hz', d:1, color:'#558b2f', yMin:0,   yMax:120},
        {key:'c_op',  label:'P. compr. out',   unit:'kW', scale:0.001, d:2, color:'#ad1457', yMin:0, yMax:35},
        {key:'c_ip',  label:'P. compr. in',    unit:'kW', scale:0.001, d:2, color:'#d81b60', yMin:0, yMax:35},
        {key:'c_oc',  label:'I. compr. out',   unit:'A',  d:1, color:'#ef6c00', yMin:0,   yMax:20},
        {key:'c_ic',  label:'I. compr. in',    unit:'A',  d:1, color:'#fb8c00', yMin:0,   yMax:20},
        {key:'c_ov',  label:'U. compr. out',   unit:'V',  d:0, color:'#5d4037', yMin:0,   yMax:400},
        {key:'c_iv',  label:'U. compr. in',    unit:'V',  d:0, color:'#795548', yMin:0,   yMax:400},
        {key:'gas_r290_conc', label:'Conc. R290', unit:'%LFL', d:1, color:'#ff6f00', yMin:0, yMax:100},
        {key:'gas_g20_conc',  label:'Conc. G20',  unit:'%LFL', d:1, color:'#00acc1', yMin:0, yMax:100}
    ]
};
var RT_PAC_CHART = {
    title:'PAC', h:360,
    series:[
        {sfx:'p_hp',   label:'P. HP',          unit:'bar', d:1, color:'#c62828', yMin:0,   yMax:50},
        {sfx:'p_bp',   label:'P. BP',          unit:'bar', d:1, color:'#1565c0', yMin:0,   yMax:50},
        {sfx:'t_bp',   label:'T° BP',         unit:'°C', d:1, color:'#2e7d32', yMin:-30, yMax:120},
        {sfx:'t_hph',  label:'T° HPc',        unit:'°C', d:1, color:'#e65100', yMin:-30, yMax:120},
        {sfx:'t_hpc',  label:'T° HPf',        unit:'°C', d:1, color:'#6a1b9a', yMin:-30, yMax:120},
        {sfx:'t_evap', label:'T° évap.',      unit:'°C', d:1, color:'#00838f', yMin:-30, yMax:120},
        {sfx:'t_cond', label:'T° cond.',      unit:'°C', d:1, color:'#4e342e', yMin:-30, yMax:120},
        {sfx:'t_oh',   label:'T° surchauffe', unit:'°C', d:1, color:'#880e4f', yMin:-30, yMax:120},
        {sfx:'t_ib',  label:'T° sortie PAC', unit:'°C', d:1, color:'#1b5e20', yMin:-30, yMax:120}
    ]
};
var SNAP_BOIL_CHART = {
    title:'Chaudière', h:360,
    series:[
        {key:'t_ib',  label:'T In Chaudière',     unit:'°C', d:1, color:'#c62828', yMin:-30, yMax:120},
        {key:'t_ob',  label:'T out Chaudière',    unit:'°C', d:1, color:'#e65100', yMin:-30, yMax:120},
        {key:'t_sb',  label:'T fumées',           unit:'°C', d:1, color:'#6a1b9a', yMin:-30, yMax:200},
        {key:'t_e',   label:'T extérieure',       unit:'°C', d:1, color:'#9e9d24', yMin:-30, yMax:120},
        {key:'wf_b',  label:'Débit eau',          unit:'L/h', d:0, color:'#1565c0', yMin:0, yMax:5000},
        {key:'wp_b',  label:'Pression eau',       unit:'bar', d:1, color:'#2e7d32', yMin:0, yMax:6},
        {key:'b_fan', label:'Vitesse brûleur',    unit:'rpm', d:0, color:'#00838f', yMin:0, yMax:10000},
        {key:'pb_dp', label:'Delta P pompe',      unit:'mCE', d:1, color:'#37474f', yMin:0, yMax:10},
        {key:'pb_wf', label:'Débit pompe',        unit:'m³/h', d:2, color:'#0d47a1', yMin:0, yMax:5},
        {key:'pb_e',  label:'Energie pompe',      unit:'kWh', d:0, color:'#558b2f', yMin:0, yMax:1000},
        {key:'pb_pw', label:'Puissance pompe',    unit:'W',   d:0, color:'#ad1457', yMin:0, yMax:200}
    ]
};
var RT_BOIL_CHART = {
    title:'Chaudière', h:360,
    series:[
        {sfx:'t_ob',  label:'T° sortie chaud.', unit:'°C', d:1, color:'#c62828', yMin:-30, yMax:120},
        {sfx:'wp_b', label:'P eau',             unit:'bar', d:2, color:'#2e7d32', yMin:-0.6, yMax:4},
        {sfx:'b_fan',   label:'V. brûleur',      unit:'rpm', d:0, color:'#00838f', yMin:0,    yMax:10000},
        {sfx:'wf_b',    label:'Débit chaud.',    unit:'L/h', d:0, color:'#1565c0', yMin:0,    yMax:5000},
        {sfx:'pb_dp',    label:'Pompe ΔP',        unit:'bar', d:2, color:'#37474f', yMin:-0.6, yMax:4}
    ]
};

function getToken(){ return localStorage.getItem('jwt_token'); }
function pad(n){ return n<10?('0'+n):(''+n); }
function fmtTime(ts){ var d=new Date(ts); return pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds()); }
function fmtFull(ts){ var d=new Date(ts); return pad(d.getDate())+'/'+pad(d.getMonth()+1)+'/'+(''+d.getFullYear()).slice(2)+' '+pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds()); }
function metaFor(k){ return KEY_META[k] || {l:k,u:'',s:1,d:0}; }
function fmtVal(k,v){
    if(v==null||isNaN(v)) return '—';
    var m=metaFor(k);
    var n = v*m.s;
    var em = ENUM_LABELS[k];
    if (em){
        var key = (n === Math.floor(n)) ? n : v;
        if (em[key] != null) return key+' — '+em[key];
        if (em[v] != null) return v+' — '+em[v];
    }
    return n.toFixed(m.d);
}

// Une cellule est « en défaut » (valeur rouge) si :
//  - clé enum dont le libellé contient fault/défaut (ex p_s=6 « fault gaz »)
//  - sinon valeur affichée négative (sentinelles capteurs -99.x, pressions < 0)
function isFaultCell(k, raw){
    if (raw==null || isNaN(raw)) return false;
    var m = metaFor(k);
    var n = raw * m.s;
    var em = ENUM_LABELS[k];
    if (em){
        var ek = (n===Math.floor(n)) ? n : raw;
        var lab = (em[ek]!=null) ? em[ek] : em[raw];
        return !!(lab && /faul|d[ée]faut/i.test(lab));
    }
    return n < 0;
}
function fmtDur(sec){
    sec = Math.round(sec);
    if (sec < 60) return sec + ' s';
    var mm = Math.floor(sec/60), ss = sec%60;
    return ss ? (mm + ' min ' + ss + ' s') : (mm + ' min');
}

function computeSnapSeries(name, series){
    if (name === 'pac_pwr'){
        var V = series.c_ov, I = series.c_oc;
        if (!V || !I || !V.length || !I.length) return null;
        var n = Math.min(V.length, I.length);
        var sV = metaFor('c_ov').s, sI = metaFor('c_oc').s;
        var SQ3 = Math.sqrt(3), result = [];
        for (var i = 0; i < n; i++) result.push((V[i]*sV) * (I[i]*sI) * SQ3 * 0.9 / 1000);
        return result;
    }
    return null;
}

self._renderHeader = function(){
    var c = self._ctx;
    var lbl = FAULT_LABELS[c.evtFault]; if (lbl===undefined) lbl='Code '+c.evtFault;
    var resolved = (c.evtType===4);
    return "<div class='fdiag-header'>"+
        "<button class='fdiag-back' id='fdiag-back'>‹ Retour</button>"+
        "<div class='fdiag-meta'>"+
          "<div class='topline'><span class='"+(resolved?'pill resolved':'pill')+"'>"+(resolved?'RÉSOLU':'DÉFAUT')+"</span>"+
          "<span>Code "+c.evtFault+(c.evtDevice?(' · Device '+c.evtDevice):'')+"</span></div>"+
          "<div class='label'>"+lbl+"</div>"+
          "<div class='when'>Survenu le <b>"+(c.evtDate||fmtFull(c.evtTs))+"</b> à <b>"+(c.evtTime||fmtTime(c.evtTs))+"</b>"+
          " · capture +30 s · fenêtre 5 min 30 s @ 1 Hz</div>"+
          (self._snapTs ? "<div class='when'>Données envoyées vers le <b>"+fmtFull(c.evtTs+30000)+"</b> · ts snapshot DB <b>"+fmtFull(self._snapTs)+"</b></div>" : "")+
          "<div class='when' style='opacity:0.55;font-size:10px;'>widget build " + (window.FDIAG_BUILD || 'spec-2026-05-13-faultsrc') + "</div>"+
        "</div>"+
      "</div>";
};
window.FDIAG_BUILD = 'spec-2026-05-13-faultsrc';

self._attachBack = function(){
    var back = self.ctx.$container[0].querySelector('#fdiag-back');
    if (!back) return;
    back.addEventListener('click', function(){
        try {
            var sc = self.ctx.stateController;
            sc.navigatePrevState(Math.max(0, sc.getStateIndex() - 1));
        } catch(e){
            try { self.ctx.stateController.openState('historique', {}, false); } catch(e2){}
        }
    });
};

self.onInit = function(){
    var ctx = self.ctx;
    ctx.$container.addClass('fdiag-host');
    ctx.$container.html("<div class='fdiag-wrap'><div class='fdiag-loader'>Chargement…</div></div>");
    self._load();
};

self._deviceId = function(){
    try{
        var sp = self.ctx.stateController && self.ctx.stateController.getStateParams() || {};
        if (sp.deviceId) return sp.deviceId;
        var ds = self.ctx.datasources && self.ctx.datasources[0];
        if (ds && ds.entityId) return ds.entityId;
        if (ds && ds.entity && ds.entity.id) return ds.entity.id.id;
    }catch(e){}
    return null;
};

self._load = function(){
    var sp = self.ctx.stateController && self.ctx.stateController.getStateParams() || {};
    var devId = self._deviceId();
    var evtTs = parseInt(sp.evtTs || 0);
    var evtFault = parseInt(sp.evtFault || 0);
    var evtType  = parseInt(sp.evtType || 1);
    var evtId    = parseInt(sp.evtId || 0);
    var evtDate  = sp.evtDate || '';
    var evtTime  = sp.evtTime || '';
    var evtDevice = parseInt(sp.evtDevice || 0);
    // evtResolvedTs : timestamp TB de la résolution (passé depuis events-history).
    // Le snapshot est envoyé au moment de la résolution, pas de l'apparition.
    var evtResolvedTs = parseInt(sp.evtResolvedTs || 0);
    // evtFaultSrc : 0=pac, 1=chaudière, 2=les deux. -1 = absent (anciens événements
    // sans la clé fault_src → comportement legacy : trait rouge sur les deux courbes).
    var evtFaultSrc = (sp.evtFaultSrc === undefined || sp.evtFaultSrc === null || sp.evtFaultSrc === '') ? -1 : parseInt(sp.evtFaultSrc);
    if (isNaN(evtFaultSrc)) evtFaultSrc = -1;
    if (!devId || !evtTs){
        self.ctx.$container.find('.fdiag-wrap').html("<div class='fdiag-empty'>Paramètres manquants : impossible de charger le défaut.</div>");
        return;
    }
    self._ctx = {devId:devId, evtTs:evtTs, evtFault:evtFault, evtType:evtType, evtId:evtId, evtDate:evtDate, evtTime:evtTime, evtDevice:evtDevice, evtResolvedTs:evtResolvedTs, evtFaultSrc:evtFaultSrc};
    self._snapFallback = false;

    // Étape 1 : trouver le ts du snapshot lié à ce défaut.
    // Le snapshot est envoyé ~8 s après la résolution (type=4). On centre la probe
    // sur evtResolvedTs si connu, sinon sur evtTs (défaut actif ou événement autonome).
    var probeKeys = ['p_bp','p_hp','t_bp','t_hph','wp_b','b_s','pb_spd','pe_spd'];
    // Le snapshot est timestampé ~20-30 s AVANT l'apparition (début de la fenêtre
    // capturée par le device, pas l'instant d'envoi). On ancre donc sur evtTs
    // (apparition) avec une fenêtre asymétrique : surtout vers le passé.
    var probeAnchor = evtTs;
    var winStart = probeAnchor - 120000;
    var winEnd   = probeAnchor + 60000;
    var url1 = '/api/plugins/telemetry/DEVICE/'+devId+'/values/timeseries?keys='+probeKeys.join(',')+
               '&startTs='+winStart+'&endTs='+winEnd+'&limit=20&agg=NONE';
    fetch(url1, { headers:{'X-Authorization':'Bearer '+getToken()} })
      .then(function(r){return r.json();})
      .then(function(probe){
          // Choix du snapshot : le plus proche temporellement de probeAnchor
          var best = null;
          probeKeys.forEach(function(k){
              var arr = probe[k] || [];
              arr.forEach(function(p){
                  var dist = Math.abs(p.ts - probeAnchor);
                  if (best == null || dist < best.dist) best = { ts: p.ts, dist: dist };
              });
          });
          var snapTs = best ? best.ts : null;
          if (!snapTs){
              // Pas de snapshot dans la fenêtre : message d'erreur explicite, pas de fallback realtime.
              var hdr = self._renderHeader();
              var msg = "<div class='fdiag-empty' style='padding:40px;font-style:normal;'>"+
                  "<div style='font-size:15px;font-weight:700;color:#c62828;margin-bottom:8px;'>Aucun snapshot disponible pour ce défaut</div>"+
                  "<div style='color:#666;font-size:13px;'>Le device n'a pas envoyé de snapshot dans les ±2 min autour de l'apparition du défaut.</div>"+
                  "<div style='color:#888;font-size:12px;margin-top:12px;'>Cause probable : firmware verrouillé après un défaut précédent (en attente de remise à zéro).</div>"+
                  "</div>";
              self.ctx.$container.html("<div class='fdiag-wrap'>"+hdr+msg+"</div>");
              self._attachBack();
              return;
          }
          self._fetchSnapshot(snapTs);
      })
      .catch(function(e){
          self.ctx.$container.find('.fdiag-wrap').html("<div class='fdiag-empty'>Erreur chargement : "+e.message+"</div>");
      });
};

self._fetchSnapshot = function(snapTs){
    var devId = self._ctx.devId;
    var allKeys = Object.keys(KEY_META);
    // batch: TB accepte des listes longues mais on découpe par 60 par sécurité
    var batches=[]; for (var i=0;i<allKeys.length;i+=60) batches.push(allKeys.slice(i,i+60));
    var window = 1500;
    Promise.all(batches.map(function(b){
        var url='/api/plugins/telemetry/DEVICE/'+devId+'/values/timeseries?keys='+b.join(',')+
                '&startTs='+(snapTs-window)+'&endTs='+(snapTs+window)+'&limit=1&agg=NONE';
        return fetch(url,{headers:{'X-Authorization':'Bearer '+getToken()}}).then(function(r){return r.json();});
    })).then(function(parts){
        var merged={};
        parts.forEach(function(p){ for (var k in p) merged[k]=p[k]; });
        var series={};
        for (var k in merged){
            if (!merged[k] || !merged[k].length) continue;
            var raw = merged[k][0].value;
            try{
                var arr = (typeof raw === 'string' && raw.charAt(0)==='[') ? JSON.parse(raw) : (Array.isArray(raw)?raw:[Number(raw)]);
                if (Array.isArray(arr) && arr.length) series[k] = arr.map(Number);
            }catch(e){}
        }
        self._snapTs = snapTs;
        self._series = series;
        self._render();
    }).catch(function(e){
        self.ctx.$container.find('.fdiag-wrap').html("<div class='fdiag-empty'>Erreur chargement données : "+e.message+"</div>");
    });
};

// groups : [{label, vals:[number], unit, d, color}]
// n : nombre de points, faultIdx : indice du défaut, chartH : hauteur SVG

function _fdiagOverlay(lbls, VW){
    var ov = "<div class='fdiag-axis-ov'>";
    lbls.forEach(function(l){
        var lx = (l.x/VW*100).toFixed(3);
        var tr = l.anchor==='right'?'translate(-100%,-50%)':l.anchor==='center'?'translate(-50%,-50%)':'translate(0,-50%)';
        var pad = l.anchor==='right'?'padding-right:3px;':l.anchor==='left'?'padding-left:3px;':'';
        var fw = l.weight?'font-weight:'+l.weight+';':'';
        var op = l.opacity!=null?'opacity:'+l.opacity+';':'';
        ov += "<span style='left:"+lx+"%;top:"+l.y.toFixed(1)+"px;transform:"+tr+";color:"+l.color+";font-size:"+l.size+"px;"+fw+pad+op+"'>"+l.text+"</span>";
    });
    return ov + "</div>";
}

self._multiSeriesChart = function(groups, n, faultIdx, chartH, cid){
    var active = groups.filter(function(g){ return g.vals && g.vals.length; });
    if (!active.length) return '';
    cid = cid || 'mc';
    var VW = 800, VH = chartH || 200;
    var ML = 42, MR = 10, MT = 26, MB = 26;
    var CW = VW - ML - MR, CH = VH - MT - MB;
    var N_FULL = 330, offset = Math.max(0, N_FULL - n);
    function xP(i){ return ML+(offset+i)/(N_FULL-1)*CW; }
    var yMin=Infinity, yMax=-Infinity;
    active.forEach(function(g){ g.vals.forEach(function(v){ if(v<yMin) yMin=v; if(v>yMax) yMax=v; }); });
    if(yMin===yMax){ yMin-=1; yMax+=1; }
    var yPad=(yMax-yMin)*0.08; yMin-=yPad; yMax+=yPad; var yRange=yMax-yMin;
    var prec = yRange>100?0:yRange>10?1:yRange>1?2:3;
    function yP(v){ return MT+CH*(1-(v-yMin)/yRange); }
    var s = '<svg viewBox="0 0 '+VW+' '+VH+'" preserveAspectRatio="none" style="width:100%;height:'+VH+'px;display:block">';
    s += '<rect x="'+ML+'" y="'+MT+'" width="'+CW+'" height="'+CH+'" fill="#fafafa"/>';
    var lbls = [];
    for (var yi=0;yi<=4;yi++){
        var yv=yMin+(yi/4)*yRange, yp=yP(yv);
        s += '<line x1="'+ML+'" y1="'+yp.toFixed(1)+'" x2="'+(ML+CW)+'" y2="'+yp.toFixed(1)+'" stroke="'+(yi===0||yi===4?'#ddd':'#eee')+'" stroke-width="1"/>';
        lbls.push({x:ML-3, y:yp, text:yv.toFixed(prec), color:'#999', size:9, anchor:'right'});
    }
    s += '<line x1="'+ML+'" y1="'+MT+'" x2="'+ML+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    s += '<line x1="'+ML+'" y1="'+(MT+CH)+'" x2="'+(ML+CW)+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    for (var sec=-300;sec<=29;sec+=60){
        var gi=sec+300, li=gi-offset; if(li<0||li>=n) continue;
        var xp=ML+gi/(N_FULL-1)*CW, isZ=(sec===0);
        s += '<line x1="'+xp.toFixed(1)+'" y1="'+MT+'" x2="'+xp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="'+(isZ?'#bbb':'#eee')+'" stroke-width="'+(isZ?'1.5':'1')+'"/>';
        lbls.push({x:xp, y:MT+CH+9, text:(sec>0?'+':'')+sec+'s', color:isZ?'#666':'#aaa', size:9, anchor:'center'});
    }
    var localFault=faultIdx-offset;
    if(localFault>=0&&localFault<n){
        var fxp=xP(localFault);
        s += '<line x1="'+fxp.toFixed(1)+'" y1="'+MT+'" x2="'+fxp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="#ED1C24" stroke-width="2" stroke-dasharray="5,4" opacity="0.8"/>';
        lbls.push({x:fxp, y:MT-19, text:'défaut', color:'#ED1C24', size:10, weight:700, anchor:'center'});
        lbls.push({x:fxp, y:MT-7, text:'▼', color:'#ED1C24', size:10, weight:700, anchor:'center'});
    }
    active.forEach(function(g,i){
        var pts=g.vals.map(function(v,j){return xP(j).toFixed(1)+','+yP(v).toFixed(1);}).join(' ');
        s += '<polyline id="fdiag-pl-'+cid+'-'+i+'" fill="none" stroke="'+g.color+'" stroke-width="1.2" stroke-linejoin="round" stroke-linecap="round" points="'+pts+'"/>';
    });
    s += '</svg>';
    var leg = "<div class='fdiag-cleg'>";
    active.forEach(function(g,i){
        var atIdx=faultIdx>=0?Math.min(faultIdx,g.vals.length-1):g.vals.length-1;
        var atV=g.vals[atIdx].toFixed(g.d!=null?g.d:1);
        leg += "<div class='fdiag-cleg-e' data-series-id='"+cid+"-"+i+"'>"+
               "<div class='fdiag-cleg-sw' style='background:"+g.color+"'></div>"+
               "<div><span class='fdiag-cleg-val' style='color:"+g.color+"'>"+atV+" <span class='fdiag-cleg-unit'>"+g.unit+"</span></span>"+
               "<span class='fdiag-cleg-lbl'>"+g.label+"</span></div></div>";
    });
    leg += "</div>";
    return "<div class='fdiag-svg-host' style='height:"+VH+"px;'>"+s+_fdiagOverlay(lbls,VW)+"</div>"+leg;
};

self._normalizedChart = function(groups, n, faultIdx, chartH, cid, showFault){
    if (showFault === undefined) showFault = true;
    var active = groups.filter(function(g){ return g.vals && g.vals.length; });
    if (!active.length) return '';
    cid = cid || 'nc';
    var USTEP = {'°C':10,'°Ce':10,'°Cx':10,'L/h':1000,'L/min':10,'m³/h':1,'bar':1,'mCE':2,'rpm':2000,'tr/min':2000,'%':10,'Hz':20,'A':5,'V':100,'kW':5,'W':50,'kWh':100,'Pa':50,'pas':200,'':1};
    var unitMap = {};
    active.forEach(function(g){ if(!unitMap[g.unit]) unitMap[g.unit]={color:g.color,yMin:g.yMin,yMax:g.yMax,d:g.d}; });
    var units = Object.keys(unitMap);
    var nLeft = 0, nRight = 0;
    var leftUnits = [], rightUnits = [];
    var AW = 0;
    var VW = 800, VH = chartH || 300;
    var ML = 14, MR = 10, MT = 30, MB = 26;
    var CW = VW-ML-MR, CH = VH-MT-MB;
    // Tableau chronologique : index 0 = plus ancien (à gauche), index n-1 = plus récent (à droite).
    // Données toujours étirées sur toute la largeur. Plage temporelle relative au défaut :
    // hypothèse "330 pts complets = -300s..+29s" → si n<330, on a perdu le début, donc t0 = 30-n.
    var N_FULL = 330;
    var t0 = (n >= N_FULL) ? -300 : (30 - n); // sec relatif au défaut, du 1er échantillon
    var tEnd = 29;
    function xP(i){ return ML + (n>1 ? i/(n-1) : 0.5) * CW; }
    function yP(v,g){ var r=g.yMax-g.yMin; return MT+CH*(1-(v-g.yMin)/r); }
    var s = '<svg viewBox="0 0 '+VW+' '+VH+'" preserveAspectRatio="none" style="width:100%;height:'+VH+'px;display:block">';
    s += '<rect x="'+ML+'" y="'+MT+'" width="'+CW+'" height="'+CH+'" fill="#fafafa"/>';
    for (var yi=0;yi<=4;yi++){
        var yp=(MT+CH*(1-yi*0.25)).toFixed(1);
        s += '<line x1="'+ML+'" y1="'+yp+'" x2="'+(ML+CW)+'" y2="'+yp+'" stroke="'+(yi===0||yi===4?'#ddd':'#eee')+'" stroke-width="1"/>';
    }
    s += '<line x1="'+ML+'" y1="'+MT+'" x2="'+ML+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    s += '<line x1="'+ML+'" y1="'+(MT+CH)+'" x2="'+(ML+CW)+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    var lbls = [];
    var tStep = 60;
    for (var sec=Math.ceil(t0/tStep)*tStep; sec<=tEnd; sec+=tStep){
        var li = sec - t0; if(li<0||li>=n) continue;
        var xp = xP(li), isZ=(sec===0);
        s += '<line x1="'+xp.toFixed(1)+'" y1="'+MT+'" x2="'+xp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="'+(isZ?'#bbb':'#eee')+'" stroke-width="'+(isZ?'1.5':'1')+'"/>';
        lbls.push({x:xp, y:MT+CH+9, text:(sec>0?'+':'')+sec+'s', color:isZ?'#666':'#aaa', size:9, anchor:'center'});
    }
    // Marqueur défaut : t=0 ⇒ idx local = -t0 = n-30 (pour n=330 → 300)
    var localFault = -t0;
    if(showFault && localFault>=0&&localFault<n){
        var fxp=xP(localFault);
        s += '<line x1="'+fxp.toFixed(1)+'" y1="'+MT+'" x2="'+fxp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="#ED1C24" stroke-width="2" stroke-dasharray="5,4" opacity="0.8"/>';
        lbls.push({x:fxp, y:MT-19, text:'défaut', color:'#ED1C24', size:10, weight:700, anchor:'center'});
        lbls.push({x:fxp, y:MT-7, text:'▼', color:'#ED1C24', size:10, weight:700, anchor:'center'});
    }
    active.forEach(function(g,i){
        var pts=g.vals.map(function(v,j){var c=Math.max(g.yMin,Math.min(g.yMax,v));return xP(j).toFixed(1)+','+yP(c,g).toFixed(1);}).join(' ');
        s += '<polyline id="fdiag-pl-'+cid+'-'+i+'" fill="none" stroke="'+g.color+'" stroke-width="1.2" stroke-linejoin="round" stroke-linecap="round" points="'+pts+'"/>';
    });
    function drawAxis(unit, ug, ax, side){
        var step = USTEP[unit]||Math.max(1,(ug.yMax-ug.yMin)/4);
        var tk2 = side==='left'?ax+3:ax-3;
        var anchor = side==='left' ? 'right' : 'left';
        lbls.push({x:ax, y:MT-18, text:unit, color:ug.color, size:9, weight:700, anchor:anchor, opacity:0.95});
        // axe vertical et graduations masqués : valeurs disponibles via crosshair/tooltip
    }
    leftUnits.forEach(function(unit,k){ drawAxis(unit,unitMap[unit],ML-(k*AW)-AW*0.5,'left'); });
    rightUnits.forEach(function(unit,k){ drawAxis(unit,unitMap[unit],ML+CW+(k*AW)+AW*0.5,'right'); });
    s += '</svg>';
    var leg = "<div class='fdiag-cleg'>";
    active.forEach(function(g,i){
        var atIdx = (localFault>=0 && localFault<g.vals.length) ? localFault : g.vals.length-1;
        var atRaw = g.vals[atIdx];
        var atV = atRaw.toFixed(g.d!=null?g.d:1);
        var atF = atRaw < 0;
        var rng = (g.yMin!=null && g.yMax!=null) ? (g.yMin+'–'+g.yMax+(g.unit?' '+g.unit:'')) : '';
        leg += "<div class='fdiag-cleg-e' data-series-id='"+cid+"-"+i+"'>"+
               "<span class='fdiag-cleg-sw' style='background:"+g.color+"'></span>"+
               "<span class='fdiag-cleg-name'>"+g.label+"</span>"+
               "<span class='fdiag-cleg-val"+(atF?' fault':'')+"'>"+atV+(g.unit?"<span class='fdiag-cleg-unit'>"+g.unit+"</span>":'')+"</span>"+
               (rng?"<span class='fdiag-cleg-range'>"+rng+"</span>":'')+"</div>";
    });
    leg += "</div>";
    self._chartCtx = self._chartCtx || {};
    self._chartCtx[cid] = {type:'snap', n:n, t0:t0, ML:ML, CW:CW, VW:VW,
        series: active.map(function(g){return {label:g.label,color:g.color,unit:g.unit,d:g.d,vals:g.vals};})};
    return "<div class='fdiag-svg-host' data-cid='"+cid+"' style='height:"+VH+"px;'>"+s+_fdiagOverlay(lbls,VW)+
           "<div class='fdiag-crosshair'></div><div class='fdiag-tooltip'></div></div>"+leg;
};

self._rtNormalizedChart = function(groups, evtTs, chartH, cid, showFault){
    if (showFault === undefined) showFault = true;
    var active = groups.filter(function(g){ return g.pts && g.pts.length; });
    if (!active.length) return '';
    cid = cid || 'rnc';
    var USTEP = {'°C':10,'°Ce':10,'°Cx':10,'L/h':1000,'L/min':10,'m³/h':1,'bar':1,'mCE':2,'rpm':2000,'tr/min':2000,'%':10,'Hz':20,'A':5,'V':100,'kW':5,'W':50,'kWh':100,'Pa':50,'pas':200,'':1};
    var unitMap = {};
    active.forEach(function(g){ if(!unitMap[g.unit]) unitMap[g.unit]={color:g.color,yMin:g.yMin,yMax:g.yMax,d:g.d}; });
    var units = Object.keys(unitMap);
    var nLeft = 0, nRight = 0;
    var leftUnits = [], rightUnits = [];
    var AW = 0;
    var VW = 800, VH = chartH || 300;
    var ML = 14, MR = 10, MT = 30, MB = 26;
    var CW = VW-ML-MR, CH = VH-MT-MB;
    var tMin=Infinity, tMax=-Infinity;
    active.forEach(function(g){ g.pts.forEach(function(p){ if(p.ts<tMin) tMin=p.ts; if(p.ts>tMax) tMax=p.ts; }); });
    if(tMin===tMax){ tMax=tMin+60000; }
    var tRange=tMax-tMin;
    function xP(ts){ return ML+((ts-tMin)/tRange)*CW; }
    function yP(v,g){ var r=g.yMax-g.yMin; return MT+CH*(1-(v-g.yMin)/r); }
    function fmtT(ts){ var d=new Date(ts); return (d.getHours()<10?'0':'')+d.getHours()+':'+(d.getMinutes()<10?'0':'')+d.getMinutes(); }
    var s = '<svg viewBox="0 0 '+VW+' '+VH+'" preserveAspectRatio="none" style="width:100%;height:'+VH+'px;display:block">';
    s += '<rect x="'+ML+'" y="'+MT+'" width="'+CW+'" height="'+CH+'" fill="#fafafa"/>';
    for (var yi=0;yi<=4;yi++){
        var yp=(MT+CH*(1-yi*0.25)).toFixed(1);
        s += '<line x1="'+ML+'" y1="'+yp+'" x2="'+(ML+CW)+'" y2="'+yp+'" stroke="'+(yi===0||yi===4?'#ddd':'#eee')+'" stroke-width="1"/>';
    }
    s += '<line x1="'+ML+'" y1="'+MT+'" x2="'+ML+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    s += '<line x1="'+ML+'" y1="'+(MT+CH)+'" x2="'+(ML+CW)+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    var lbls = [];
    var xMs=5*60000, tL=Math.ceil(tMin/xMs)*xMs;
    for(var t=tL;t<=tMax;t+=xMs){
        var xp=xP(t);
        s += '<line x1="'+xp.toFixed(1)+'" y1="'+MT+'" x2="'+xp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="#eee" stroke-width="1"/>';
        lbls.push({x:xp, y:MT+CH+9, text:fmtT(t), color:'#aaa', size:9, anchor:'center'});
    }
    if(showFault && evtTs>=tMin&&evtTs<=tMax){
        var fxp=xP(evtTs);
        s += '<line x1="'+fxp.toFixed(1)+'" y1="'+MT+'" x2="'+fxp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="#ED1C24" stroke-width="2" stroke-dasharray="5,4" opacity="0.8"/>';
        lbls.push({x:fxp, y:MT-19, text:'défaut', color:'#ED1C24', size:10, weight:700, anchor:'center'});
        lbls.push({x:fxp, y:MT-7, text:'▼', color:'#ED1C24', size:10, weight:700, anchor:'center'});
    }
    active.forEach(function(g,i){
        if(g.pts.length===1){
            var c=Math.max(g.yMin,Math.min(g.yMax,g.pts[0].v));
            s += '<circle id="fdiag-pl-'+cid+'-'+i+'" cx="'+xP(g.pts[0].ts).toFixed(1)+'" cy="'+yP(c,g).toFixed(1)+'" r="5" fill="'+g.color+'"/>';
        } else {
            var pts=g.pts.map(function(p){var c=Math.max(g.yMin,Math.min(g.yMax,p.v));return xP(p.ts).toFixed(1)+','+yP(c,g).toFixed(1);}).join(' ');
            s += '<polyline id="fdiag-pl-'+cid+'-'+i+'" fill="none" stroke="'+g.color+'" stroke-width="1.2" stroke-linejoin="round" stroke-linecap="round" points="'+pts+'"/>';
            g.pts.forEach(function(p){var c=Math.max(g.yMin,Math.min(g.yMax,p.v));s+='<circle cx="'+xP(p.ts).toFixed(1)+'" cy="'+yP(c,g).toFixed(1)+'" r="3" fill="'+g.color+'" opacity="0.8"/>';});
        }
    });
    function drawAxis(unit, ug, ax, side){
        var step = USTEP[unit]||Math.max(1,(ug.yMax-ug.yMin)/4);
        var tk2 = side==='left'?ax+3:ax-3;
        var anchor = side==='left' ? 'right' : 'left';
        lbls.push({x:ax, y:MT-18, text:unit, color:ug.color, size:9, weight:700, anchor:anchor, opacity:0.95});
        // axe vertical et graduations masqués : valeurs disponibles via crosshair/tooltip
    }
    leftUnits.forEach(function(unit,k){ drawAxis(unit,unitMap[unit],ML-(k*AW)-AW*0.5,'left'); });
    rightUnits.forEach(function(unit,k){ drawAxis(unit,unitMap[unit],ML+CW+(k*AW)+AW*0.5,'right'); });
    s += '</svg>';
    var leg = "<div class='fdiag-cleg'>";
    active.forEach(function(g,i){
        var atFault=g.pts.reduce(function(b,p){return Math.abs(p.ts-evtTs)<Math.abs(b.ts-evtTs)?p:b;},g.pts[0]).v;
        var atF = atFault < 0;
        var rng = (g.yMin!=null && g.yMax!=null) ? (g.yMin+'–'+g.yMax+(g.unit?' '+g.unit:'')) : '';
        leg += "<div class='fdiag-cleg-e' data-series-id='"+cid+"-"+i+"'>"+
               "<span class='fdiag-cleg-sw' style='background:"+g.color+"'></span>"+
               "<span class='fdiag-cleg-name'>"+g.label+"</span>"+
               "<span class='fdiag-cleg-val"+(atF?' fault':'')+"'>"+atFault.toFixed(g.d!=null?g.d:1)+(g.unit?"<span class='fdiag-cleg-unit'>"+g.unit+"</span>":'')+"</span>"+
               (rng?"<span class='fdiag-cleg-range'>"+rng+"</span>":'')+"</div>";
    });
    leg += "</div>";
    self._chartCtx = self._chartCtx || {};
    self._chartCtx[cid] = {type:'rt', tMin:tMin, tMax:tMax, ML:ML, CW:CW, VW:VW,
        series: active.map(function(g){return {label:g.label,color:g.color,unit:g.unit,d:g.d,pts:g.pts};})};
    return "<div class='fdiag-svg-host' data-cid='"+cid+"' style='height:"+VH+"px;'>"+s+_fdiagOverlay(lbls,VW)+
           "<div class='fdiag-crosshair'></div><div class='fdiag-tooltip'></div></div>"+leg;
};

self._rtMultiSeriesChart = function(groups, evtTs, chartH, cid){
    var active = groups.filter(function(g){ return g.pts && g.pts.length; });
    if (!active.length) return '';
    cid = cid || 'rmc';
    var VW = 800, VH = chartH || 200;
    var ML = 42, MR = 10, MT = 26, MB = 26;
    var CW = VW - ML - MR, CH = VH - MT - MB;
    var tMin=Infinity, tMax=-Infinity, yMin=Infinity, yMax=-Infinity;
    active.forEach(function(g){ g.pts.forEach(function(p){
        if(p.ts<tMin) tMin=p.ts; if(p.ts>tMax) tMax=p.ts;
        if(p.v<yMin) yMin=p.v; if(p.v>yMax) yMax=p.v;
    }); });
    if(tMin===tMax){ tMax=tMin+60000; }
    if(yMin===yMax){ yMin-=1; yMax+=1; }
    var yPad=(yMax-yMin)*0.08; yMin-=yPad; yMax+=yPad; var yRange=yMax-yMin;
    var tRange=tMax-tMin;
    var prec=yRange>100?0:yRange>10?1:yRange>1?2:3;
    function xP(ts){ return ML+((ts-tMin)/tRange)*CW; }
    function yP(v){ return MT+CH*(1-(v-yMin)/yRange); }
    function fmtT(ts){ var d=new Date(ts); return (d.getHours()<10?'0':'')+d.getHours()+':'+(d.getMinutes()<10?'0':'')+d.getMinutes(); }
    var s = '<svg viewBox="0 0 '+VW+' '+VH+'" preserveAspectRatio="none" style="width:100%;height:'+VH+'px;display:block">';
    s += '<rect x="'+ML+'" y="'+MT+'" width="'+CW+'" height="'+CH+'" fill="#fafafa"/>';
    var lbls = [];
    for (var yi=0;yi<=4;yi++){
        var yv=yMin+(yi/4)*yRange, yp=yP(yv);
        s += '<line x1="'+ML+'" y1="'+yp.toFixed(1)+'" x2="'+(ML+CW)+'" y2="'+yp.toFixed(1)+'" stroke="'+(yi===0||yi===4?'#ddd':'#eee')+'" stroke-width="1"/>';
        lbls.push({x:ML-3, y:yp, text:yv.toFixed(prec), color:'#999', size:9, anchor:'right'});
    }
    s += '<line x1="'+ML+'" y1="'+MT+'" x2="'+ML+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    s += '<line x1="'+ML+'" y1="'+(MT+CH)+'" x2="'+(ML+CW)+'" y2="'+(MT+CH)+'" stroke="#ccc" stroke-width="1.5"/>';
    var xMs=5*60000, tL=Math.ceil(tMin/xMs)*xMs;
    for(var t=tL;t<=tMax;t+=xMs){
        var xp=xP(t);
        s += '<line x1="'+xp.toFixed(1)+'" y1="'+MT+'" x2="'+xp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="#eee" stroke-width="1"/>';
        lbls.push({x:xp, y:MT+CH+9, text:fmtT(t), color:'#aaa', size:9, anchor:'center'});
    }
    if(evtTs>=tMin&&evtTs<=tMax){
        var fxp=xP(evtTs);
        s += '<line x1="'+fxp.toFixed(1)+'" y1="'+MT+'" x2="'+fxp.toFixed(1)+'" y2="'+(MT+CH)+'" stroke="#ED1C24" stroke-width="2" stroke-dasharray="5,4" opacity="0.8"/>';
        lbls.push({x:fxp, y:MT-19, text:'défaut', color:'#ED1C24', size:10, weight:700, anchor:'center'});
        lbls.push({x:fxp, y:MT-7, text:'▼', color:'#ED1C24', size:10, weight:700, anchor:'center'});
    }
    active.forEach(function(g,i){
        if(g.pts.length===1){
            s += '<circle id="fdiag-pl-'+cid+'-'+i+'" cx="'+xP(g.pts[0].ts).toFixed(1)+'" cy="'+yP(g.pts[0].v).toFixed(1)+'" r="5" fill="'+g.color+'"/>';
        } else {
            var pts=g.pts.map(function(p){return xP(p.ts).toFixed(1)+','+yP(p.v).toFixed(1);}).join(' ');
            s += '<polyline id="fdiag-pl-'+cid+'-'+i+'" fill="none" stroke="'+g.color+'" stroke-width="1.2" stroke-linejoin="round" stroke-linecap="round" points="'+pts+'"/>';
            g.pts.forEach(function(p){s+='<circle cx="'+xP(p.ts).toFixed(1)+'" cy="'+yP(p.v).toFixed(1)+'" r="3" fill="'+g.color+'" opacity="0.8"/>';});
        }
    });
    s += '</svg>';
    var leg = "<div class='fdiag-cleg'>";
    active.forEach(function(g,i){
        var atFault=g.pts.reduce(function(b,p){return Math.abs(p.ts-evtTs)<Math.abs(b.ts-evtTs)?p:b;},g.pts[0]).v;
        leg += "<div class='fdiag-cleg-e' data-series-id='"+cid+"-"+i+"'>"+
               "<div class='fdiag-cleg-sw' style='background:"+g.color+"'></div>"+
               "<div><span class='fdiag-cleg-val' style='color:"+g.color+"'>"+atFault.toFixed(g.d!=null?g.d:1)+" <span class='fdiag-cleg-unit'>"+g.unit+"</span></span>"+
               "<span class='fdiag-cleg-lbl'>"+g.label+"</span></div></div>";
    });
    leg += "</div>";
    return "<div class='fdiag-svg-host' style='height:"+VH+"px;'>"+s+_fdiagOverlay(lbls,VW)+"</div>"+leg;
};


self._attachChartToggles = function(){
    var container = self.ctx.$container[0];
    Array.prototype.forEach.call(container.querySelectorAll('[data-series-id]'), function(el){
        el.addEventListener('click', function(){
            var sid = el.getAttribute('data-series-id');
            var pl = container.querySelector('#fdiag-pl-'+sid);
            if (!pl) return;
            var hidden = el.getAttribute('data-hidden') === '1';
            el.setAttribute('data-hidden', hidden ? '0' : '1');
            pl.style.opacity = hidden ? '1' : '0.06';
            el.style.opacity = hidden ? '1' : '0.3';
        });
    });
};

self._attachHover = function(){
    var container = self.ctx.$container[0];
    var ctxMap = self._chartCtx || {};
    Array.prototype.forEach.call(container.querySelectorAll('.fdiag-svg-host[data-cid]'), function(host){
        var cid = host.getAttribute('data-cid');
        var ctx = ctxMap[cid]; if (!ctx) return;
        var ch = host.querySelector('.fdiag-crosshair');
        var tt = host.querySelector('.fdiag-tooltip');
        if (!ch || !tt) return;
        function p2(n){return n<10?'0'+n:''+n;}
        host.addEventListener('mousemove', function(e){
            var rect = host.getBoundingClientRect();
            var px = e.clientX - rect.left, py = e.clientY - rect.top;
            var sx = px * ctx.VW / rect.width;
            if (sx < ctx.ML || sx > ctx.ML + ctx.CW){ ch.style.display='none'; tt.style.display='none'; return; }
            var rel = (sx - ctx.ML) / ctx.CW;
            var crossPx = (ctx.ML + rel*ctx.CW) / ctx.VW * rect.width;
            ch.style.left = crossPx+'px'; ch.style.display = 'block';

            // Build hidden-series set from legend toggles
            var hidden = {};
            Array.prototype.forEach.call(container.querySelectorAll(".fdiag-cleg-e[data-series-id^='"+cid+"-']"), function(le){
                if (le.getAttribute('data-hidden')==='1'){
                    var sid = le.getAttribute('data-series-id');
                    hidden[parseInt(sid.split('-').pop(), 10)] = true;
                }
            });

            var rows = [], timeLabel;
            if (ctx.type === 'snap'){
                var idx = Math.max(0, Math.min(ctx.n-1, Math.round(rel * (ctx.n-1))));
                var sec = ctx.t0 + idx;
                timeLabel = (sec>0?'+':'') + sec + ' s ' + (sec===0?'(défaut)':sec<0?'avant':'après');
                ctx.series.forEach(function(s,si){
                    if (hidden[si]) return;
                    var v = s.vals[idx]; if (v==null||isNaN(v)) return;
                    rows.push("<div class='fdiag-tooltip-row'><span><span class='fdiag-tooltip-sw' style='background:"+s.color+"'></span>"+s.label+"</span><span>"+v.toFixed(s.d!=null?s.d:1)+" "+s.unit+"</span></div>");
                });
            } else {
                var ts = ctx.tMin + rel * (ctx.tMax - ctx.tMin);
                var d = new Date(ts);
                timeLabel = p2(d.getHours())+':'+p2(d.getMinutes())+':'+p2(d.getSeconds());
                ctx.series.forEach(function(s,si){
                    if (hidden[si]) return;
                    var best = null;
                    s.pts.forEach(function(p){ if (!best || Math.abs(p.ts-ts)<Math.abs(best.ts-ts)) best = p; });
                    if (!best) return;
                    rows.push("<div class='fdiag-tooltip-row'><span><span class='fdiag-tooltip-sw' style='background:"+s.color+"'></span>"+s.label+"</span><span>"+best.v.toFixed(s.d!=null?s.d:1)+" "+s.unit+"</span></div>");
                });
            }
            tt.innerHTML = "<div class='fdiag-tooltip-time'>"+timeLabel+"</div>"+rows.join('');

            var ttW = 240;
            var ttX = crossPx + 12;
            if (ttX + ttW > rect.width) ttX = crossPx - ttW - 12;
            ttX = Math.max(4, ttX);
            tt.style.left = ttX+'px';
            tt.style.top = Math.max(4, Math.min(rect.height - 250, py - 30))+'px';
            tt.style.display = 'block';
        });
        host.addEventListener('mouseleave', function(){
            ch.style.display='none'; tt.style.display='none';
        });
    });
};


self._kpiHtml = function(){ return ''; };

self._sectionTablesHtml = function(sectionTitle){
    if (!self._series) return '';
    var defs = SECTION_TABLES[sectionTitle] || [];
    var out = '';
    defs.forEach(function(def){
        var cells = [];
        def.keys.forEach(function(k){
            var arr = self._series[k]; if (!arr || !arr.length) return;
            // Le snapshot capture 30 points (30 s) APRÈS l'apparition du défaut,
            // donc l'instant du défaut est arr.length-30 (et non un index figé).
            var idx = Math.max(0, Math.min(arr.length-1, arr.length-30));
            var atFault = arr[idx];
            var m = metaFor(k);
            var ok = (atFault!=null && !isNaN(atFault));
            var v = ok ? fmtVal(k, atFault) : '—';
            var fault = ok && isFaultCell(k, atFault);
            var uHtml = (ok && m.u) ? "<span class='fdiag-du'>"+m.u+"</span>" : '';
            cells.push("<div class='fdiag-dcell'>"+
                         "<span class='fdiag-dk'>"+m.l+"</span>"+
                         "<span class='fdiag-dv"+(fault?' fault':'')+"'>"+v+uHtml+"</span>"+
                       "</div>");
        });
        if (!cells.length) return;
        out += "<div class='fdiag-vcard'>"+
                 "<div class='fdiag-vcard-head'>"+def.title+" — au moment du défaut</div>"+
                 "<div class='fdiag-dgrid'>"+cells.join('')+"</div>"+
               "</div>";
    });
    return out;
};

// Mapping evt_device → HP prefix (50=HP1, 51=HP2…)
function hpPfx(evtDevice){
    // __FAULT_DIAG_KEYMAP_PATCH__ : les debug arrays autour des defauts utilisent des
    // keys snake_case sans prefixe HP{N}_. Le mapping HP{N}_ camelCase n'est
    // plus pertinent depuis migration v2.
    return '';
}

var RT_GROUPS = [
    {title:'Pressions',    keys:['pLo','pHi']},
    {title:'Températures', keys:['tLP','tOut','tHPf','tHPh','tOH','tEvap','tCond']},
    {title:'Compresseur',  keys:['rpm','status']},
    {title:'Pompe',        keys:['pump_dP','pump_rpm']},
    {title:'Chaudière',    keys:['boil_tOut','boil_press','boil_status','boil_rpm','boil_qe']},
];
var RT_META_BASE = {
    pLo:{l:'P BP',u:'bar',d:1}, pHi:{l:'P HP',u:'bar',d:1},
    tLP:{l:'T LP',u:'°C',d:1}, tOut:{l:'T sortie',u:'°C',d:1},
    tHPf:{l:'T HP froid',u:'°C',d:1}, tHPh:{l:'T HP chaud',u:'°C',d:1},
    tOH:{l:'Surchauffe',u:'°C',d:1}, tEvap:{l:'T évap.',u:'°C',d:1},
    tCond:{l:'T cond.',u:'°C',d:1},
    rpm:{l:'Vitesse compr.',u:'tr/min',d:0}, status:{l:'État PAC',u:'',d:0},
    pump_dP:{l:'Pompe ΔP',u:'bar',d:2}, pump_rpm:{l:'Pompe',u:'tr/min',d:0},
    boil_tOut:{l:'Chaud. T sortie',u:'°C',d:1}, boil_press:{l:'Chaud. pression',u:'bar',d:2},
    boil_status:{l:'État chaudière',u:'',d:0}, boil_rpm:{l:'Chaud. tr/min',u:'tr/min',d:0},
    boil_qe:{l:'Chaud. débit',u:'L/h',d:0},
};

self._fetchRealtime = function(){
    var c = self._ctx;
    var pfx = hpPfx(c.evtDevice);
    var allSuffixes = [];
    RT_PAC_CHART.series.forEach(function(s){ if(s.sfx) allSuffixes.push(s.sfx); });
    RT_BOIL_CHART.series.forEach(function(s){ if(s.sfx) allSuffixes.push(s.sfx); });
    var keys = allSuffixes.map(function(s){ return pfx + s; });
    // Centrer sur evtResolvedTs (snapshot envoyé à la résolution) quand dispo,
    // sinon sur evtTs. Fenêtre ±10 min pour capturer la télémétrie 1/min.
    var probeTs = (c.evtResolvedTs && c.evtResolvedTs > 0) ? c.evtResolvedTs : c.evtTs;
    var winStart = probeTs - 600000;
    var winEnd   = probeTs + 600000;
    self.ctx.$container.html("<div class='fdiag-wrap'><div class='fdiag-loader'>Chargement télémétrie…</div></div>");
    fetch('/api/plugins/telemetry/DEVICE/'+c.devId+'/values/timeseries?keys='+keys.join(',')+'&startTs='+winStart+'&endTs='+winEnd+'&limit=50&agg=NONE',
        {headers:{'X-Authorization':'Bearer '+getToken()}})
      .then(function(r){return r.json();})
      .then(function(raw){
          // __FAULT_DIAG_ARRAY_PATCH__ : expand arrays str_v -> N points temporels
          // Spec user : N valeurs etalees sur [evtTs - 180s, evtTs + 30s]
          // (3 min avant defaut + 30 s apres). 1 valeur = scalar a evtTs.
          var series = {};
          var WIN_BEFORE_MS = 180000;
          var WIN_AFTER_MS  = 30000;
          var SEND_DELAY_MS = 30000;
          var SPAN_MS = WIN_BEFORE_MS + WIN_AFTER_MS;
          for (var k in raw){
              var pts = [];
              (raw[k]||[]).forEach(function(p){
                  var rv = p.value;
                  var arr;
                  try {
                      if (typeof rv === 'string' && rv.charAt(0) === '[') {
                          arr = JSON.parse(rv);
                      } else if (Array.isArray(rv)) {
                          arr = rv;
                      } else {
                          arr = [Number(rv)];
                      }
                  } catch(e) { arr = [Number(rv)]; }
                  if (!Array.isArray(arr) || !arr.length) return;
                  var anchor = (c.evtTs && c.evtTs > 0) ? c.evtTs : (p.ts - SEND_DELAY_MS);
                  var n = arr.length;
                  if (n === 1) {
                      var v0 = Number(arr[0]);
                      if (!isNaN(v0) && v0 > -99) pts.push({ts: anchor, v: v0});
                      return;
                  }
                  var step = SPAN_MS / (n - 1);
                  for (var i = 0; i < n; i++) {
                      var v = Number(arr[i]);
                      if (isNaN(v) || v <= -99) continue;
                      pts.push({ts: (anchor - WIN_BEFORE_MS) + i * step, v: v});
                  }
              });
              pts.sort(function(a,b){return a.ts - b.ts;});
              if (pts.length) series[k] = pts;
          }
          self._rtSeries = series;
          self._pfx = pfx;
          self._renderRealtime();
      })
      .catch(function(e){
          self.ctx.$container.find('.fdiag-wrap').html("<div class='fdiag-empty'>Erreur chargement : "+e.message+"</div>");
      });
};

self._renderRealtime = function(){
    var c = self._ctx;
    var series = self._rtSeries;
    var pfx = self._pfx;
    var evtTs = c.evtTs;
    var cidCtr = 0;
    self._chartCtx = {};

    // fault_src : 0=pac, 1=chaudière, 2=les deux. -1 (absent) → comportement legacy : sur les deux.
    var fs = c.evtFaultSrc;
    var showPac  = (fs === -1 || fs === 0 || fs === 2);
    var showBoil = (fs === -1 || fs === 1 || fs === 2);
    function normalizedRtSec(title, chartDef, prefix, showFault){
        var groups = [];
        chartDef.series.forEach(function(def){
            var pts;
            if (def.sfx) {
                pts = series[pfx+def.sfx];
                if (!pts || !pts.length) return;
            } else { return; }
            groups.push({label:def.label, pts:pts, unit:def.unit, d:def.d, color:def.color, yMin:def.yMin, yMax:def.yMax});
        });
        if (!groups.length) return '';
        return "<div class='fdiag-sec'><div class='fdiag-seclabel'>"+title+"</div></div>"+
               "<div class='fdiag-chartcard'>"+
                 "<div class='fdiag-chartcard-head'><span>"+title+" — télémétrie autour du défaut</span></div>"+
                 "<div class='fdiag-chartcard-body'><div class='fdiag-chart-wrap'>"+
                   self._rtNormalizedChart(groups, evtTs, chartDef.h, prefix+(++cidCtr), showFault)+
                 "</div></div>"+
               "</div>";
    }
    var sectionsHtml = normalizedRtSec('PAC', RT_PAC_CHART, 'rp', showPac) + normalizedRtSec('Chaudière', RT_BOIL_CHART, 'rb', showBoil);
    if (!sectionsHtml){
        sectionsHtml = "<div class='fdiag-empty'>Aucune donnée disponible. <button id='fdiag-retry' style='margin-top:10px;padding:4px 12px;border-radius:6px;border:1px solid #ccc;cursor:pointer;'>⟳ Réessayer</button></div>";
    }

    var probeTs = (c.evtResolvedTs && c.evtResolvedTs > 0) ? c.evtResolvedTs : c.evtTs;
    var pd = new Date(probeTs);
    var pp2 = function(n){return n<10?'0'+n:''+n;};
    var pFmt = pp2(pd.getDate())+'/'+pp2(pd.getMonth()+1)+'/'+(''+pd.getFullYear()).slice(2)+' '+pp2(pd.getHours())+':'+pp2(pd.getMinutes())+':'+pp2(pd.getSeconds());
    var pLabel = (c.evtResolvedTs && c.evtResolvedTs > 0) ? 'résolution' : 'apparition';
    var notice = "<div class='fdiag-notice'>"+
        "Télémétrie temps-réel · fenêtre ±10 min autour de la <b>"+pLabel+"</b> ("+pFmt+") · pas de snapshot disponible</div>";

    var html = "<div class='fdiag-wrap'>"+self._renderHeader()+notice+self._kpiHtml()+sectionsHtml+"</div>";
    self.ctx.$container.html(html);
    self._attachBack();
    self._attachChartToggles();
    self._attachHover();
    var btn = self.ctx.$container[0].querySelector('#fdiag-retry');
    if (btn) btn.addEventListener('click', function(){ self._load(); });
};

self._render = function(){
    var faultIdx = 300;
    var n = 0;
    var cidCtr = 0;
    self._chartCtx = {};
    Object.keys(self._series).forEach(function(k){ if(self._series[k].length>n) n=self._series[k].length; });

    // fault_src : 0=pac, 1=chaudière, 2=les deux. -1 (absent) → comportement legacy : sur les deux.
    var fs = self._ctx.evtFaultSrc;
    var showPac  = (fs === -1 || fs === 0 || fs === 2);
    var showBoil = (fs === -1 || fs === 1 || fs === 2);
    function normalizedSnapSec(title, chartDef, prefix, showFault){
        var groups = [];
        chartDef.series.forEach(function(def){
            var vals;
            var arr = self._series[def.key]; if(!arr||!arr.length) return;
            var m = metaFor(def.key);
            var sc = def.scale!=null ? def.scale : m.s;
            var vals = arr.map(function(v){return v*sc;});
            groups.push({label:def.label, vals:vals, unit:def.unit, d:def.d, color:def.color, yMin:def.yMin, yMax:def.yMax});
        });
        if (!groups.length) return '';
        var t0 = (n >= 330) ? -300 : (30 - n);
        var wStart = self._ctx.evtTs + t0*1000;
        var wEnd = self._ctx.evtTs + 29000;
        var headTxt = title+" — fenêtre de capture "+fmtFull(wStart)+" → "+fmtTime(wEnd)+" ("+fmtDur(n-1)+" @ 1 Hz)";
        return "<div class='fdiag-sec'>"+
                 "<div class='fdiag-seclabel'>"+title+"</div>"+
                 self._sectionTablesHtml(title)+
               "</div>"+
               "<div class='fdiag-chartcard'>"+
                 "<div class='fdiag-chartcard-head'><span>"+headTxt+"</span></div>"+
                 "<div class='fdiag-chartcard-body'><div class='fdiag-chart-wrap'>"+
                   self._normalizedChart(groups, n, faultIdx, chartDef.h, prefix+(++cidCtr), showFault)+
                 "</div></div>"+
               "</div>";
    }
    var bodyHtml = normalizedSnapSec('PAC', SNAP_PAC_CHART, 'sp', showPac) + normalizedSnapSec('Chaudière', SNAP_BOIL_CHART, 'sb', showBoil);
    if (!bodyHtml) bodyHtml = "<div class='fdiag-empty'>Aucune s\u00e9rie dans le snapshot.</div>";

    var noticeHtml = '';
    if (self._snapFallback){
        var sd = new Date(self._snapTs);
        var sp = function(x){return x<10?'0'+x:''+x;};
        var snapFmt = sp(sd.getDate())+'/'+sp(sd.getMonth()+1)+'/'+(''+sd.getFullYear()).slice(2)+' '+sp(sd.getHours())+':'+sp(sd.getMinutes())+':'+sp(sd.getSeconds());
        noticeHtml = "<div class='fdiag-notice'>"+
            "Snapshot le plus r\u00e9cent \u00b7 captur\u00e9 le <b>"+snapFmt+"</b> \u00b7 aucun snapshot au moment du d\u00e9faut</div>";
    }

    var html = "<div class='fdiag-wrap'>"+self._renderHeader()+noticeHtml+self._kpiHtml()+bodyHtml+"</div>";
    self.ctx.$container.html(html);
    self._attachBack();
    self._attachChartToggles();
    self._attachHover();
};

self._expand = function(key){
    var arr = self._series[key]; if (!arr) return;
    var m = metaFor(key);
    var n = arr.length;
    var thead = "<thead><tr><th>#</th><th>t&nbsp;(s)</th><th>"+key+(m.u?" ("+m.u+")" : "")+"</th></tr></thead>";
    var tbody = "<tbody>";
    for (var i = 0; i < n; i++){
        var tRel = i - 300;
        var rowCls = (i === 300) ? " class='fdiag-fault-row'" : "";
        tbody += "<tr"+rowCls+"><td>"+i+"</td><td>"+(tRel>=0?"+":"")+tRel+"</td><td>"+fmtVal(key,arr[i])+"</td></tr>";
    }
    tbody += "</tbody>";
    var modal = document.createElement('div');
    modal.className = 'fdiag-modal';
    modal.innerHTML =
        "<div class='fdiag-modal-inner'>"+
            "<div class='fdiag-modal-head'><div class='t'>"+m.l+(m.u?" ("+m.u+")" : "")+"</div><button class='fdiag-modal-close'>×</button></div>"+
            "<div class='fdiag-modal-body' style='padding:0'>"+
                "<div class='fdiag-tbl-wrap' style='max-height:75vh'>"+
                    "<table class='fdiag-dtbl'>"+thead+tbody+"</table>"+
                "</div>"+
            "</div>"+
        "</div>";
    document.body.appendChild(modal);
    function close(){ if (modal.parentNode) modal.parentNode.removeChild(modal); }
    modal.addEventListener('click', function(e){ if (e.target===modal) close(); });
    modal.querySelector('.fdiag-modal-close').addEventListener('click', close);
};

self.onResize = function(){};
self.onDestroy = function(){};
