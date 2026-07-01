///
/// Copyright © 2016-2026 The Thingsboard Authors
///
/// Licensed under the Apache License, Version 2.0 (the "License");
/// you may not use this file except in compliance with the License.
/// You may obtain a copy of the License at
///
///     http://www.apache.org/licenses/LICENSE-2.0
///
/// Unless required by applicable law or agreed to in writing, software
/// distributed under the License is distributed on an "AS IS" BASIS,
/// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
/// See the License for the specific language governing permissions and
/// limitations under the License.
///

import {
    MenuId,
    MenuSection,
    YAHTEC_ADMIN_OPS_HIDDEN_MENU_IDS,
    yahtecFilterAdminOpsMenu
} from './menu.models';

const makeSection = (id: MenuId, pages?: Array<MenuSection>): MenuSection => ({
    id,
    name: id,
    type: 'link',
    path: '/' + id,
    icon: 'home',
    ...(pages ? { pages } : {})
});

describe('yahtecFilterAdminOpsMenu', () => {
    it('retire les sections dev présentes dans YAHTEC_ADMIN_OPS_HIDDEN_MENU_IDS', () => {
        const sections: MenuSection[] = [
            makeSection(MenuId.dashboards),
            makeSection(MenuId.rule_chains),
            makeSection(MenuId.device_profiles),
            makeSection(MenuId.customers)
        ];
        const result = yahtecFilterAdminOpsMenu(sections, YAHTEC_ADMIN_OPS_HIDDEN_MENU_IDS);
        expect(result.map(s => s.id)).toEqual([MenuId.dashboards, MenuId.customers]);
    });

    it('garde toutes les sections si aucune ne figure dans hiddenIds', () => {
        const sections: MenuSection[] = [
            makeSection(MenuId.dashboards),
            makeSection(MenuId.customers),
            makeSection(MenuId.home)
        ];
        const result = yahtecFilterAdminOpsMenu(sections, YAHTEC_ADMIN_OPS_HIDDEN_MENU_IDS);
        expect(result.length).toBe(3);
    });

    it('filtre récursivement les pages enfants', () => {
        const sections: MenuSection[] = [
            makeSection(MenuId.resources, [
                makeSection(MenuId.widget_library),
                makeSection(MenuId.images)
            ]),
            makeSection(MenuId.dashboards)
        ];
        const result = yahtecFilterAdminOpsMenu(sections, YAHTEC_ADMIN_OPS_HIDDEN_MENU_IDS);
        // resources doit rester (son id n'est pas dans la liste), mais widget_library doit être retiré des pages
        expect(result.length).toBe(2);
        const resources = result.find(s => s.id === MenuId.resources);
        expect(resources).toBeDefined();
        expect(resources.pages.map(p => p.id)).toEqual([MenuId.images]);
    });

    it('retourne un tableau vide si toutes les sections sont cachées', () => {
        const sections: MenuSection[] = [
            makeSection(MenuId.rule_chains),
            makeSection(MenuId.calculated_fields)
        ];
        const result = yahtecFilterAdminOpsMenu(sections, YAHTEC_ADMIN_OPS_HIDDEN_MENU_IDS);
        expect(result.length).toBe(0);
    });

    it('ne modifie pas les sections sans portfolioRole (non-ADMIN_OPS)', () => {
        // Simuler l'appel uniquement si portfolioRole=ADMIN_OPS — ici on teste que
        // la fonction pure retourne les sections inchangées si hiddenIds = []
        const sections: MenuSection[] = [
            makeSection(MenuId.rule_chains),
            makeSection(MenuId.dashboards)
        ];
        const result = yahtecFilterAdminOpsMenu(sections, []);
        expect(result.length).toBe(2);
    });
});
