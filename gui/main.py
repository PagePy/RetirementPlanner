"""Planificateur de retraite — application NiceGUI.

Lancement: python run_app.py
"""
from nicegui import ui

from gui import state as state_mod
from gui.pages import profile_page, patrimoine_page, resultats_page
from gui.pages import analyses_page, outils_page

# Toutes les fenêtres popup/dialog doivent être déplaçables: un
# MutationObserver global rend chaque q-dialog draggable automatiquement.
DRAGGABLE_DIALOGS_JS = """
new MutationObserver(() => {
    document.querySelectorAll('.q-dialog .q-card:not([data-draggable])')
        .forEach(card => {
            card.setAttribute('data-draggable', '1');
            card.style.cursor = 'move';
            let sx, sy, ox, oy, dragging = false;
            card.addEventListener('mousedown', e => {
                if (['INPUT','TEXTAREA','SELECT','BUTTON','LABEL'].includes(
                        e.target.tagName)) return;
                dragging = true; sx = e.clientX; sy = e.clientY;
                const r = card.getBoundingClientRect(); ox = r.left; oy = r.top;
                card.style.position = 'fixed'; card.style.margin = '0';
                card.style.left = ox + 'px'; card.style.top = oy + 'px';
                e.preventDefault();
            });
            window.addEventListener('mousemove', e => {
                if (!dragging) return;
                card.style.left = (ox + e.clientX - sx) + 'px';
                card.style.top = (oy + e.clientY - sy) + 'px';
            });
            window.addEventListener('mouseup', () => dragging = false);
        });
}).observe(document.body, {childList: true, subtree: true});
"""


def build_app():
    app_state = state_mod.default_state()

    ui.add_head_html(f"<script>window.addEventListener('load', () => {{"
                     f"{DRAGGABLE_DIALOGS_JS}}});</script>")

    with ui.header().classes("bg-primary items-center"):
        ui.label("🏖️ Planificateur de retraite").classes("text-xl font-bold")
        ui.space()
        ui.input("Nom du profil").bind_value(app_state, "profile_name") \
            .props("dark dense standout").classes("w-48")

        def do_save():
            try:
                path = state_mod.save_profile(app_state)
                ui.notify(f"Profil sauvegardé: {path.name}", type="positive")
            except Exception as exc:
                ui.notify(f"Erreur: {exc}", type="negative")

        def open_load_dialog():
            profiles = state_mod.list_profiles()
            with ui.dialog() as dialog, ui.card():
                ui.label("Charger un profil").classes("text-lg font-bold")
                ui.label("Les anciens profils Streamlit sont migrés "
                         "automatiquement.").classes("text-xs text-gray-500")

                def load(name: str):
                    try:
                        loaded = state_mod.load_profile(name)
                        app_state.clear()
                        app_state.update(loaded)
                        dialog.close()
                        ui.notify(f"Profil «{name}» chargé — rechargez la page "
                                  "pour rafraîchir les formulaires",
                                  type="positive")
                        ui.navigate.reload()
                    except Exception as exc:
                        ui.notify(f"Erreur: {exc}", type="negative")

                for name in profiles:
                    ui.button(name, on_click=lambda n=name: load(n)) \
                        .props("flat align=left").classes("w-full")
                if not profiles:
                    ui.label("Aucun profil trouvé.")
            dialog.open()

        ui.button("💾 Sauvegarder", on_click=do_save).props("flat color=white")
        ui.button("📂 Charger", on_click=open_load_dialog).props("flat color=white")

    with ui.tabs().classes("w-full") as tabs:
        tab_profil = ui.tab("👤 Profil & Comptes")
        tab_patrimoine = ui.tab("🏠 Actifs & Dettes")
        tab_resultats = ui.tab("📈 Résultats")
        tab_analyses = ui.tab("🔬 Analyses")
        tab_outils = ui.tab("🎯 Outils")

    with ui.tab_panels(tabs, value=tab_profil).classes("w-full"):
        with ui.tab_panel(tab_profil):
            profile_page.build(app_state)
        with ui.tab_panel(tab_patrimoine):
            patrimoine_page.build(app_state)
        with ui.tab_panel(tab_resultats):
            resultats_page.build(app_state)
        with ui.tab_panel(tab_analyses):
            analyses_page.build(app_state)
        with ui.tab_panel(tab_outils):
            outils_page.build(app_state)


def run_app(native: bool = False, port: int = 8090):
    build_app()
    ui.run(title="Planificateur de retraite", language="fr",
           native=native, port=port, reload=False, show=False)
