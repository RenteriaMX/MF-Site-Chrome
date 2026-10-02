"""Pruebas de las partes puras de install_site_chrome.py. Ejecutar: python3 -m unittest tests/test_install_site_chrome.py"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sc_install", RAIZ / "install_site_chrome.py")
SC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SC)

COOKIEPLONE = ("import type { ConfigType } from '@plone/registry';\nimport installSettings from './config/settings';\n\n"
               "function applyConfig(config: ConfigType) {\n  installSettings(config);\n  return config;\n}\n\nexport default applyConfig;\n")


class IndexTs(unittest.TestCase):
    def test_agrega_control_panel_ruta_y_ssr(self):
        t, e = SC.patch_index_ts(COOKIEPLONE)
        self.assertEqual(e, "ok")
        for frag in ("import SiteChromeControlPanel", "import { siteChromeReducer, siteChromeAsyncExtender }", "config.settings.navDepth = 2;",
                     "'@id': '/controlpanel/site-chrome'", "path: '/controlpanel/site-chrome'", "siteChrome: siteChromeReducer",
                     "extend: siteChromeAsyncExtender"):
            self.assertIn(frag, t)
        self.assertNotIn("installSettings(config)", t)          # se retira del cuerpo (igual que la versión en shell)
        self.assertTrue(t.rstrip().endswith("export default applyConfig;"))

    def test_idempotente(self):
        una, _ = SC.patch_index_ts(COOKIEPLONE)
        otra, estado = SC.patch_index_ts(una)
        self.assertEqual(estado, "ya"); self.assertEqual(una, otra)

    def test_respeta_reducers_y_extenders_ajenos(self):
        src = ("import type { ConfigType } from '@plone/registry';\nfunction applyConfig(config: ConfigType) {\n"
               "  config.addonReducers = { ...config.addonReducers, mio: miReducer };\n"
               "  config.settings.asyncPropsExtenders = [\n    { path: '/', extend: ajeno },\n  ];\n  return config;\n}\n")
        t, _ = SC.patch_index_ts(src)
        self.assertIn("mio: miReducer", t); self.assertIn("extend: ajeno", t)
        self.assertEqual(t.count("siteChrome: siteChromeReducer"), 1); self.assertEqual(t.count("extend: siteChromeAsyncExtender"), 1)

    def test_llaves_y_comillas_en_strings_y_comentarios_no_rompen(self):
        src = "import type { ConfigType } from '@plone/registry';\nfunction applyConfig(config: ConfigType) {\n  // { comentario con llaves\n  config.x = \"}\";\n  return config;\n}\n"
        t, _ = SC.patch_index_ts(src)
        self.assertIn('config.x = "}";', t); self.assertIn("path: '/controlpanel/site-chrome'", t)

    def test_archivo_vacio_crea_applyconfig(self):
        t, _ = SC.patch_index_ts("")
        self.assertIn("function applyConfig(config: ConfigType)", t); self.assertIn("siteChromeReducer", t)

    def test_arrow_function(self):
        t, _ = SC.patch_index_ts("import type { ConfigType } from '@plone/registry';\nconst applyConfig = (config: ConfigType) => {\n  return config;\n};\n")
        self.assertIn("siteChromeReducer", t)

    def test_migra_el_nav_menu_viejo(self):
        src = ("import NavigationMenuControlPanel from './controlpanels/NavigationMenuControlPanel';\nimport { navMenuReducer, navMenuAsyncExtender } from './navMenuSSR';\n"
               "function applyConfig(config) {\n  config.addonReducers = { ...(config.addonReducers || {}), navMenu: navMenuReducer };\n  return config;\n}\n")
        t, _ = SC.patch_index_ts(src)
        self.assertNotIn("navMenuReducer", t); self.assertNotIn("NavigationMenuControlPanel", t); self.assertIn("siteChromeReducer", t)

    def test_llaves_desbalanceadas(self):
        with self.assertRaises(SC.InstallError):
            SC.patch_index_ts("function applyConfig(config: ConfigType) {\n  return config;\n")

    def test_limpia_index_ajeno(self):
        parcheado, _ = SC.patch_index_ts(COOKIEPLONE)
        limpio = SC.clean_other_index(parcheado)
        self.assertNotIn("SiteChromeControlPanel", limpio); self.assertNotIn("site-chrome", limpio)
        self.assertIsNone(SC.clean_other_index(COOKIEPLONE))


class Parches(unittest.TestCase):
    def test_volto_config_tema_nuevo(self):
        self.assertEqual(SC.patch_volto_config_new_theme("const addons = ['a', 'b'];", "volto-t"), "const addons = ['a', 'b', 'volto-t'];")
        self.assertEqual(SC.patch_volto_config_new_theme("const addons = [];", "volto-t"), "const addons = ['volto-t'];")
        self.assertEqual(SC.patch_volto_config_new_theme("const addons = ['a',\n];", "volto-t"), "const addons = ['a', 'volto-t'];")

    def test_dnd_kit(self):
        t, a = SC.ensure_dnd_kit(json.dumps({"dependencies": {"@dnd-kit/core": "^6.1.0"}}))
        self.assertEqual(a, ["@dnd-kit/sortable", "@dnd-kit/utilities"]); self.assertEqual(SC.ensure_dnd_kit(t)[1], [])

    def test_registrar_tema_en_package_json(self):
        self.assertEqual(json.loads(SC.register_in_package_json('{"dependencies": {"a": "1"}}', "volto-t"))["dependencies"],
                         {"a": "1", "volto-t": "workspace:*"})

    def test_package_json_del_tema_nuevo(self):
        d = json.loads(SC.theme_package_json("volto-t"))
        self.assertEqual(d["name"], "volto-t"); self.assertIn("@dnd-kit/core", d["dependencies"]); self.assertEqual(d["main"], "src/index.ts")


class Deteccion(unittest.TestCase):
    def _proyecto(self, d):
        base = Path(d) / "proy"
        (base / "backend/src/mi.policy/__pycache__").mkdir(parents=True)
        (base / "backend/src/mi.egg-info").mkdir()
        for t in ("volto-b", "volto-a", "otro"):
            (base / "frontend/packages" / t).mkdir(parents=True)
        (base / "frontend/packages/volto-a/package.json").write_text(json.dumps({"description": "Tema A"}))
        return base

    def test_backend_y_temas(self):
        with tempfile.TemporaryDirectory() as d:
            base = self._proyecto(d)
            self.assertEqual(SC.detect_backend_name(base), "mi.policy")
            self.assertEqual(SC.list_themes(base), ["volto-a", "volto-b"])
            self.assertEqual(SC.theme_description(base, "volto-a"), "Tema A")

    def test_sin_backend(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SC.InstallError):
                SC.detect_backend_name(Path(d))

    def test_servicios_por_archivo_de_unidad(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "heoc"; base.mkdir(); u = Path(d) / "units"; u.mkdir()
            (u / "heoc-backend-a.service").write_text(f"[Service]\nExecStart={base}/backend/.venv/bin/runwsgi x\n")
            (u / "heoc-volto.service").write_text(f"[Service]\nWorkingDirectory={base}/frontend\nExecStart=node build/server.js\n")
            (u / "otro-proyecto.service").write_text("[Service]\nExecStart=/otro/.venv/bin/runwsgi x\n")
            svcs, modes = SC.detect_services(base, user_dir=str(Path(d) / "nada"), sys_dir=str(u))
            self.assertEqual(svcs, {"backend": ["heoc-backend-a"], "volto": ["heoc-volto"]}); self.assertEqual(modes["backend"], "system")

    def test_site_id(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plone-x-volto.service").write_text('Environment="RAZZLE_INTERNAL_API_PATH=http://localhost:8080/MiSitio/algo"\n')
            self.assertEqual(SC.detect_site_id([d]), "MiSitio")
            self.assertEqual(SC.detect_site_id([str(Path(d) / "no")]), "Plone")

    def test_plantillas_de_servicio_se_expanden_o_se_dejan(self):
        self.assertEqual(SC.expand_templates("system", ["a", "b"]), ["a", "b"])


class Fuente(unittest.TestCase):
    def test_script_embebido_es_python_valido(self):
        compile(SC.ZCONSOLE_SCRIPT, "zconsole_script", "exec")

    def test_los_archivos_del_frontend_existen_en_el_repo(self):
        for rel in ("frontend/index.ts.template", "frontend/Navigation.jsx", "frontend/Navigation.css", "frontend/Footer.jsx",
                    "frontend/Footer.css", "frontend/SiteChromeControlPanel.jsx", "frontend/SiteChromeControlPanel.css", "frontend/siteChromeSSR.js"):
            self.assertTrue((RAIZ / "src" / rel).is_file(), rel)
        self.assertTrue((RAIZ / "backend/collective.sitechrome").is_dir())


if __name__ == "__main__":
    unittest.main()
