"""Planificateur de retraite — application NiceGUI.

Lancement: python run_app.py
"""
import logging

from nicegui import ui

from gui import state as state_mod
from gui.pages import profile_page, patrimoine_page, resultats_page
from gui.pages import analyses_page, outils_page, help_page
from planner.core.data_status import warning_message

log = logging.getLogger(__name__)

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

    @ui.refreshable
    def render_pages():
        with ui.tabs().classes("w-full") as tabs:
            tab_profil = ui.tab("👤 Profil & Comptes")
            tab_patrimoine = ui.tab("🏠 Actifs & Dettes")
            tab_resultats = ui.tab("📈 Résultats")
            tab_analyses = ui.tab("🔬 Analyses")
            tab_outils = ui.tab("🎯 Outils")
            tab_aide = ui.tab("❓ Aide")

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
            with ui.tab_panel(tab_aide):
                help_page.build(app_state)

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
                log.exception("Échec de la sauvegarde du profil")
                ui.notify(f"Erreur: {exc}", type="negative")

        def open_load_dialog():
            profiles = state_mod.list_profiles()
            with ui.dialog() as dialog, ui.card():
                ui.label("Charger un profil").classes("text-lg font-bold")
                ui.label("Les anciens profils Streamlit sont migrés "
                         "automatiquement.").classes("text-xs text-gray-500")

                def apply_state(loaded: dict, message: str):
                    app_state.clear()
                    app_state.update(loaded)
                    dialog.close()
                    render_pages.refresh()
                    ui.notify(message, type="positive")

                def load(name: str):
                    try:
                        apply_state(state_mod.load_profile(name), f"Profil «{name}» chargé")
                    except Exception as exc:
                        log.exception("Échec du chargement du profil %s", name)
                        ui.notify(f"Erreur: {exc}", type="negative")

                def open_history(name: str):
                    versions = state_mod.profile_history(name)
                    with ui.dialog() as hist_dialog, ui.card().classes("min-w-[700px]"):
                        ui.label(f"Historique — {name}").classes("text-lg font-bold")
                        if not versions:
                            ui.label("Aucune version archivée (l'historique se crée à "
                                     "chaque sauvegarde qui modifie le profil).") \
                                .classes("text-gray-500")
                        current = state_mod.load_profile(name)
                        newer = current
                        for path in versions:
                            older = state_mod.load_version(path)
                            changes = state_mod.diff_states(older, newer)
                            with ui.expansion(
                                    f"{path.stem} — {len(changes)} changement(s) vers la "
                                    f"version suivante").classes("w-full"):
                                for c in changes[:60]:
                                    ui.label(f"{c['path']}: {c['old']} → {c['new']}") \
                                        .classes("text-xs font-mono")
                                if len(changes) > 60:
                                    ui.label(f"… et {len(changes) - 60} autres").classes("text-xs")

                                def restore(p=path):
                                    loaded = state_mod.load_version(p)
                                    hist_dialog.close()
                                    apply_state(loaded, f"Version {p.stem} restaurée "
                                                        "(non sauvegardée)")

                                ui.button("Restaurer cette version", on_click=restore) \
                                    .props("dense outline")
                            newer = older
                    hist_dialog.open()

                for name in profiles:
                    with ui.row().classes("items-center w-full no-wrap"):
                        ui.button(name, on_click=lambda n=name: load(n)) \
                            .props("flat align=left").classes("flex-grow")
                        ui.button(icon="history",
                                  on_click=lambda n=name: open_history(n)) \
                            .props("flat dense").tooltip("Historique des versions")
                if not profiles:
                    ui.label("Aucun profil trouvé.")
            dialog.open()

        ui.button("💾 Sauvegarder", on_click=do_save).props("flat color=white")
        ui.button("📂 Charger", on_click=open_load_dialog).props("flat color=white")

    def _warning(start_year) -> str:
        try:
            if app_state.get("hide_data_warning", False):
                return ""
            return warning_message(int(start_year or 0), app_state.get("province", "QC"))
        except Exception:
            log.exception("Statut des paramètres indisponible")
            return ""

    def dismiss_warning():
        app_state["hide_data_warning"] = True
        banner.visible = False

    with ui.row().classes("w-full items-center gap-2 bg-orange-1 text-orange-10 "
                          "px-4 py-2 text-sm") as banner:
        ui.icon("warning").classes("text-lg")
        ui.label().bind_text_from(app_state, "start_year", backward=_warning)
        ui.button(icon="close", on_click=dismiss_warning).props("flat dense round")

    def _show_warning_banner(y: int) -> bool:
        return bool(_warning(y)) and not app_state.get("hide_data_warning", False)

    banner.bind_visibility_from(app_state, "start_year",
                                backward=_show_warning_banner)

    render_pages()


def run_app(native: bool = False, port: int = 8090):
    build_app()
    ui.run(title="Planificateur de retraite", language="fr",
           native=native, port=port, reload=False, show=False)
