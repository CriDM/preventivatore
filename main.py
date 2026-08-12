__version__ = "1.0.1"
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import threading
import storage
import woo_sync
from pathlib import Path
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
from datetime import date
import datetime
import sys

import urllib.request
from packaging import version
import shutil

import platform
import os
import subprocess
import tempfile

from pdf_generator import generate_quote_pdf

TWOPLACES = Decimal("0.01")

def q(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

def parse_decimal(text: str, field_name: str) -> Decimal:
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        raise ValueError(f"Il campo '{field_name}' è obbligatorio.")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Il campo '{field_name}' deve essere numerico.") from exc

def format_decimal(value: Decimal) -> str:
    return f"{q(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class PreventivoApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("Preventivatore - Croce e Cuore ARTE SACRA")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self._icon_image = None

        # Imposta icona dell'app (cross-platform)
        self._set_window_icon()

        self.items = []
        
        # Percorso "nascosto" in stile vera app (nella home dell'utente)
        self.settings_dir = Path.home() / ".preventivatore"
        self.settings_file = self.settings_dir / "settings.json"

        self.settings = self._load_settings()
        self.woo_products = storage.load_woo_products()
        self.show_vat_var = tk.BooleanVar(value=self.settings.get("show_vat", True))
        self.show_vat_var.trace_add("write", self._save_draft)

        self._build_header()
        
        # I pulsanti in basso vengono pacchettizzati PRIMA della tabella
        # in modo che il frame della tabella non li spinga fuori dallo schermo.
        self._build_buttons()
        self._build_client_section()
        self._build_form()
        self._build_table()

        # Bindings scorciatoie globali
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Command-s>", lambda e: self.save_project())
        self.root.bind("<Control-p>", lambda e: self.generate_pdf())
        self.root.bind("<Command-p>", lambda e: self.generate_pdf())

        # Se non c'è il nome azienda, è il primo avvio
        if not self.settings.get("company_name"):
            self.root.after(500, lambda: self.open_settings_dialog(first_run=True))

        self.root.after(100, self._check_and_load_draft)
        self.root.after(2000, self._check_and_prompt_update)

    def _save_draft(self, *args) -> None:
        if getattr(self, "_loading_draft", False):
            return
        payload = {
            "customer": {
                "name": self.customer_name_var.get(),
                "address": self.customer_address_var.get(),
                "contact": self.contact_person_var.get(),
                "oggetto": self.oggetto_var.get(),
                "quote_date": self.quote_date_var.get(),
                "notes": self.final_notes_var.get(),
            },
            "show_vat": self.show_vat_var.get(),
            "items": self._serialize_items()
        }
        try:
            with open(self.settings_dir / "draft.pquote", "w", encoding="utf-8") as f:
                import json
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _delete_draft(self) -> None:
        draft_file = self.settings_dir / "draft.pquote"
        if draft_file.exists():
            try:
                draft_file.unlink()
            except Exception:
                pass


    def _check_and_prompt_update(self):
        def run_check():
            try:
                url = f"https://api.github.com/repos/CriDM/preventivatore/releases/latest"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read())

                latest_version = data['tag_name'].lstrip('v')

                if version.parse(latest_version) > version.parse(__version__):
                    assets = data.get('assets', [])
                    download_url = None

                    system = platform.system()
                    if system == "Windows":
                        for asset in assets:
                            if asset['name'].endswith('.exe'):
                                download_url = asset['browser_download_url']
                                break
                    elif system == "Darwin":
                        for asset in assets:
                            if asset['name'].endswith('.app.zip') or asset['name'].endswith('.dmg') or 'mac' in asset['name'].lower():
                                download_url = asset['browser_download_url']
                                break

                    if download_url:
                        self.root.after(0, self._show_update_dialog, latest_version, download_url)
            except Exception as e:
                print(f"Aggiornamento automatico fallito: {e}")

        threading.Thread(target=run_check, daemon=True).start()

    def _show_update_dialog(self, new_version, download_url):
        res = messagebox.askyesno(
            "Aggiornamento Disponibile",
            f"È disponibile la nuova versione {new_version}!\nVuoi scaricarla e installarla ora?",
            parent=self.root
        )
        if res:
            progress_win = tk.Toplevel(self.root)
            progress_win.title("Download in corso...")
            progress_win.geometry("300x120")
            progress_win.resizable(False, False)
            progress_win.transient(self.root)
            progress_win.grab_set()

            # Center
            progress_win.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (300 // 2)
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (120 // 2)
            progress_win.geometry(f"+{x}+{y}")

            tk.Label(progress_win, text=f"Scaricamento della versione {new_version}...").pack(pady=(15, 5))

            progress = ttk.Progressbar(progress_win, mode='indeterminate')
            progress.pack(fill=tk.X, padx=20, pady=10)
            progress.start()

            threading.Thread(target=self._download_and_install, args=(download_url, progress_win), daemon=True).start()

    def _download_and_install(self, url, progress_win):
        try:
            fd, temp_path = tempfile.mkstemp()
            os.close(fd)

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(temp_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

            progress_win.after(0, progress_win.destroy)

            system = platform.system()
            if system == "Windows":
                current_exe = sys.executable
                if not current_exe.endswith('.exe') or 'python' in os.path.basename(current_exe).lower():
                    self.root.after(0, messagebox.showinfo, "Download completato",
                               f"Aggiornamento scaricato in:\n{temp_path}\nSostituiscilo manualmente.",
                               parent=self.root)
                    return

                batch_script = f"""@echo off
echo Attendere l'aggiornamento di Preventivatore...
timeout /t 2 /nobreak > NUL
move /Y "{temp_path}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
                fd_bat, bat_path = tempfile.mkstemp(suffix=".bat")
                with os.fdopen(fd_bat, 'w') as f:
                    f.write(batch_script)

                flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                subprocess.Popen([bat_path], shell=True, creationflags=flags)
                self.root.after(0, self.root.destroy)

            elif system == "Darwin":
                subprocess.Popen(['open', temp_path])
                self.root.after(0, messagebox.showinfo, "Aggiornamento scaricato",
                           "L'aggiornamento è stato scaricato. Segui le istruzioni a schermo per completare l'installazione.",
                           parent=self.root)
            else:
                self.root.after(0, messagebox.showinfo, "Download completato",
                           f"Aggiornamento scaricato in:\n{temp_path}\nInstallalo manualmente.",
                           parent=self.root)

        except Exception as e:
            progress_win.after(0, progress_win.destroy)
            self.root.after(0, messagebox.showerror, "Errore", f"Impossibile installare l'aggiornamento: {e}", parent=self.root)

    def _check_and_load_draft(self) -> None:
        draft_file = self.settings_dir / "draft.pquote"
        if draft_file.exists():
            if messagebox.askyesno("Bozza trovata", "È stato trovato un preventivo non salvato in precedenza. Vuoi ripristinarlo?"):
                self._loading_draft = True
                try:
                    import json
                    with open(draft_file, "r", encoding="utf-8") as f:
                        payload = json.load(f)

                    cust = payload.get("customer", {})
                    self.customer_name_var.set(cust.get("name", ""))
                    self.customer_address_var.set(cust.get("address", ""))
                    self.contact_person_var.set(cust.get("contact", ""))
                    self.oggetto_var.set(cust.get("oggetto", ""))
                    self.quote_date_var.set(cust.get("quote_date", ""))
                    self.final_notes_var.set(cust.get("notes", ""))
                    if "show_vat" in payload:
                        self.show_vat_var.set(bool(payload["show_vat"]))
                        self._on_vat_toggle()

                    # Reset items
                    self.items = []
                    for item in self.tree.get_children():
                        self.tree.delete(item)

                    items_data = payload.get("items", [])
                    for i_data in items_data:
                        name = i_data.get("name", "")
                        price = parse_decimal(str(i_data.get("unit_price", "0")), "Prezzo")
                        qty = parse_decimal(str(i_data.get("quantity", "0")), "Quantità")
                        vat = parse_decimal(str(i_data.get("vat_percent", "0")), "IVA")

                        tot_riga = price * qty
                        iva_riga = tot_riga * (vat / Decimal("100"))
                        tot_con_iva = tot_riga + iva_riga

                        self.items.append({
                            "name": name,
                            "unit_price": price,
                            "quantity": qty,
                            "total": tot_riga,
                            "vat_percent": vat,
                            "total_with_vat": tot_con_iva
                        })
                        self.tree.insert("", "end", values=(
                            name,
                            format_decimal(price),
                            format_decimal(qty),
                            format_decimal(tot_riga),
                            format_decimal(vat),
                            format_decimal(tot_con_iva),
                        ))
                    self._refresh_summary()
                except Exception as e:
                    messagebox.showerror("Errore", f"Impossibile caricare la bozza: {e}")
                finally:
                    self._loading_draft = False
            else:
                self._delete_draft()


    def _load_settings(self) -> dict:
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "company_name": "",
            "company_address": "",
            "piva": "",
            "email": "",
            "phone": "",
            "logo_path": "",
            "quote_number": "1",
            "woo_url": "",
            "woo_key": "",
            "woo_secret": ""
        }

    def _set_window_icon(self) -> None:
        """Carica l'icona della finestra (cross-platform: macOS, Windows, Linux)."""
        try:
            assets_dir = self._get_assets_dir()
            
            # Su Windows: prova ICO con iconbitmap()
            if platform.system() == "Windows":
                try:
                    import ctypes
                    myappid = 'croceecuore.preventivatore.1.0'
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
                except Exception:
                    pass

                ico_path = assets_dir / "icon.ico"
                if ico_path.exists():
                    try:
                        # Usa il path assoluto e converte a string in formato Windows
                        icon_abs_path = str(ico_path.resolve())
                        self.root.iconbitmap(default=icon_abs_path)
                        return
                    except (tk.TclError, OSError):
                        pass  # Se fallisce, prova PNG
                
                # Se ICO non funziona, prova PNG su Windows
                png_path = assets_dir / "icon.png"
                if png_path.exists():
                    try:
                        # Carica PNG con PhotoImage
                        photo = tk.PhotoImage(file=str(png_path.resolve()))
                        self._icon_image = photo
                        self.root.iconphoto(False, photo)
                        return
                    except (tk.TclError, OSError):
                        pass
            
            # Su macOS e Linux: preferisci PNG con iconphoto()
            if platform.system() in ("Darwin", "Linux"):
                png_path = assets_dir / "icon.png"
                if png_path.exists():
                    try:
                        photo = tk.PhotoImage(file=str(png_path.resolve()))
                        self._icon_image = photo
                        self.root.iconphoto(False, photo)
                        return
                    except (tk.TclError, OSError):
                        pass
        except (tk.TclError, OSError):
            pass  # Se non riesce, continua senza icona (non critico)

    def _get_assets_dir(self) -> Path:
        # In PyInstaller one-file i file aggiuntivi sono estratti in _MEIPASS.
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        return base_path / "assets"

    def _save_settings(self) -> None:
        self.settings_dir.mkdir(exist_ok=True)
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            messagebox.showerror("Errore di salvataggio", f"Impossibile salvare le impostazioni:\n{exc}")

    def open_settings_dialog(self, first_run=False) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Setup Dati Azienda" if first_run else "Impostazioni Azienda")
        dialog.geometry("800x650")
        dialog.transient(self.root)
        dialog.grab_set()

        if first_run:
            ttk.Label(
                dialog, 
                text="Benvenuto! Inserisci i dati della tua azienda. Li salveremo per sempre.", 
                font=("Helvetica", 10, "bold")
            ).pack(pady=(10, 5))

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Nome Azienda:").grid(row=0, column=0, sticky="w", pady=5)
        name_var = tk.StringVar(value=self.settings.get("company_name", ""))
        ttk.Entry(frame, textvariable=name_var, width=40).grid(row=0, column=1, pady=5)

        ttk.Label(frame, text="Indirizzo:").grid(row=1, column=0, sticky="w", pady=5)
        addr_var = tk.StringVar(value=self.settings.get("company_address", ""))
        ttk.Entry(frame, textvariable=addr_var, width=40).grid(row=1, column=1, pady=5)

        ttk.Label(frame, text="Partita IVA:").grid(row=2, column=0, sticky="w", pady=5)
        piva_var = tk.StringVar(value=self.settings.get("piva", ""))
        ttk.Entry(frame, textvariable=piva_var, width=40).grid(row=2, column=1, pady=5)

        ttk.Label(frame, text="Email:").grid(row=3, column=0, sticky="w", pady=5)
        email_var = tk.StringVar(value=self.settings.get("email", ""))
        ttk.Entry(frame, textvariable=email_var, width=40).grid(row=3, column=1, pady=5)

        ttk.Label(frame, text="Telefono:").grid(row=4, column=0, sticky="w", pady=5)
        phone_var = tk.StringVar(value=self.settings.get("phone", ""))
        ttk.Entry(frame, textvariable=phone_var, width=40).grid(row=4, column=1, pady=5)

        logo_var = tk.StringVar(value=self.settings.get("logo_path", ""))
        ttk.Label(frame, text="Logo Predefinito:").grid(row=5, column=0, sticky="w", pady=5)
        
        logo_frame = ttk.Frame(frame)
        logo_frame.grid(row=5, column=1, sticky="ew", pady=5)
        ttk.Entry(logo_frame, textvariable=logo_var, state="readonly").pack(side="left", fill="x", expand=True)
        
        def choose_default_logo():
            path = filedialog.askopenfilename(
                filetypes=[
                    ("Loghi supportati", ("*.png", "*.jpg", "*.jpeg", "*.svg")),
                    ("SVG", "*.svg"),
                    ("PNG", "*.png"),
                    ("JPEG", ("*.jpg", "*.jpeg")),
                    ("Tutti i file", "*.*"),
                ]
            )
            if path:
                logo_var.set(path)

        ttk.Button(logo_frame, text="Sfoglia...", command=choose_default_logo).pack(side="right", padx=(5,0))

        def save_and_close():
            self.settings["company_name"] = name_var.get().strip()
            self.settings["company_address"] = addr_var.get().strip()
            self.settings["piva"] = piva_var.get().strip()
            self.settings["email"] = email_var.get().strip()
            self.settings["phone"] = phone_var.get().strip()
            self.settings["logo_path"] = logo_var.get().strip()
            self.settings["woo_url"] = woo_url_var.get().strip()
            self.settings["woo_key"] = woo_key_var.get().strip()
            self.settings["woo_secret"] = woo_secret_var.get().strip()
            self._save_settings()
            dialog.destroy()


        ttk.Separator(frame, orient="horizontal").grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(frame, text="Integrazione WooCommerce", font=("Helvetica", 10, "bold")).grid(row=7, column=0, columnspan=2, sticky="w", pady=5)

        ttk.Label(frame, text="URL Sito (es. https://miosito.it):").grid(row=8, column=0, sticky="w", pady=5)
        woo_url_var = tk.StringVar(value=self.settings.get("woo_url", ""))
        ttk.Entry(frame, textvariable=woo_url_var, width=40).grid(row=8, column=1, pady=5)

        ttk.Label(frame, text="Consumer Key:").grid(row=9, column=0, sticky="w", pady=5)
        woo_key_var = tk.StringVar(value=self.settings.get("woo_key", ""))
        ttk.Entry(frame, textvariable=woo_key_var, width=40).grid(row=9, column=1, pady=5)

        ttk.Label(frame, text="Consumer Secret:").grid(row=10, column=0, sticky="w", pady=5)
        woo_secret_var = tk.StringVar(value=self.settings.get("woo_secret", ""))
        ttk.Entry(frame, textvariable=woo_secret_var, width=40, show="*").grid(row=10, column=1, pady=5)

        sync_lbl = ttk.Label(frame, text="")
        sync_lbl.grid(row=11, column=1, sticky="w", pady=5)

        def run_sync():
            url = woo_url_var.get().strip()
            key = woo_key_var.get().strip()
            secret = woo_secret_var.get().strip()
            if not url or not key or not secret:
                messagebox.showerror("Errore", "Inserisci URL, Key e Secret per sincronizzare.")
                return

            sync_btn.config(state="disabled")
            sync_lbl.config(text="Sincronizzazione in corso...", foreground="blue")

            def update_status(msg):
                self.root.after(0, lambda: sync_lbl.config(text=msg))

            def fetch_thread():
                try:
                    products = woo_sync.fetch_woocommerce_products(url, key, secret, update_callback=update_status)
                    storage.save_woo_products(products)
                    self.woo_products = products
                    self.root.after(0, self._update_woo_autocomplete)
                except Exception as e:
                    self.root.after(0, lambda: sync_lbl.config(text=f"Errore: {e}", foreground="red"))
                finally:
                    self.root.after(0, lambda: sync_btn.config(state="normal"))

            threading.Thread(target=fetch_thread, daemon=True).start()

        sync_btn = ttk.Button(frame, text="🔄 Sincronizza Prodotti", command=run_sync)
        sync_btn.grid(row=11, column=0, pady=5, sticky="w")


        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=12, column=0, columnspan=2, pady=20)

        ttk.Button(btn_frame, text="Salva Impostazioni", command=save_and_close).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Esporta Settings", command=self.export_settings).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Importa Settings", command=lambda: self.import_settings(dialog)).pack(side="left", padx=5)

    def export_settings(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Settings", "*.json")], initialfile="preventivatore_settings.json")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Successo", "Impostazioni esportate correttamente!")
        except Exception as exc:
            messagebox.showerror("Errore", f"Impossibile esportare le impostazioni:\n{exc}")

    def import_settings(self, dialog: tk.Toplevel) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON Settings", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                new_settings = json.load(f)

            # Merge settings
            self.settings.update(new_settings)
            self._save_settings()

            messagebox.showinfo("Successo", "Impostazioni importate correttamente!")

            # Close dialog and reopen to reflect changes
            dialog.destroy()
            self.open_settings_dialog()

        except Exception as exc:
            messagebox.showerror("Errore", f"Impossibile importare le impostazioni:\n{exc}")

    def increment_quote_number(self):
        current = self.quote_number_var.get().strip()
        try:
            new_num = int(current) + 1
            self.quote_number_var.set(str(new_num))
            self.settings["quote_number"] = str(new_num)
            self._save_settings()
        except ValueError:
            self.settings["quote_number"] = current
            self._save_settings()
            messagebox.showinfo("Salvato", "Formato testo salvato come predefinito.")

    def _build_header(self) -> None:
        header_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        header_frame.pack(fill="x", padx=12, pady=(12, 0))
        
        ctk.CTkLabel(header_frame, text="Compilazione Nuovo Preventivo", font=ctk.CTkFont(family="Helvetica", size=18, weight="bold")).pack(side="left")
        ctk.CTkButton(header_frame, text="⚙️ Impostazioni Azienda", command=self.open_settings_dialog).pack(side="right")

    def _build_client_section(self) -> None:
        frame_container = ctk.CTkFrame(self.root)
        frame_container.pack(fill="x", padx=12, pady=(8, 8))

        ctk.CTkLabel(frame_container, text="Dati Documento e Cliente", font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")).pack(anchor="w", padx=12, pady=(8,0))

        frame = ctk.CTkFrame(frame_container, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=(0, 12))

        self.quote_number_var = tk.StringVar(value=self.settings.get("quote_number", "1"))
        self.quote_date_var = tk.StringVar(value=str(date.today().strftime("%d/%m/%Y")))
        

        self.customer_name_var = tk.StringVar()
        self.customer_address_var = tk.StringVar()
        self.contact_person_var = tk.StringVar()
        self.oggetto_var = tk.StringVar()
        self.final_notes_var = tk.StringVar(value="")

        # Traces for auto-save
        self.customer_name_var.trace_add("write", self._save_draft)
        self.customer_address_var.trace_add("write", self._save_draft)
        self.contact_person_var.trace_add("write", self._save_draft)
        self.oggetto_var.trace_add("write", self._save_draft)
        self.final_notes_var.trace_add("write", self._save_draft)
        self.quote_date_var.trace_add("write", self._save_draft)


        # Riga 1: N. Preventivo e Data
        ctk.CTkLabel(frame, text="Num. Preventivo:").grid(row=0, column=0, sticky="w", padx=(0, 5), pady=4)
        num_frame = ctk.CTkFrame(frame, fg_color="transparent")
        num_frame.grid(row=0, column=1, sticky="w", padx=(0, 15), pady=4)
        ctk.CTkEntry(num_frame, textvariable=self.quote_number_var, width=100).pack(side="left")
        ctk.CTkButton(num_frame, text="+1 Salva", command=self.increment_quote_number, width=80).pack(side="left", padx=(5, 0))

        ctk.CTkLabel(frame, text="Data:").grid(row=0, column=2, sticky="w", padx=(0, 5), pady=4)
        ctk.CTkEntry(frame, textvariable=self.quote_date_var, width=150).grid(row=0, column=3, sticky="w", pady=4)

        # Riga 2: Cliente e Indirizzo
        ctk.CTkLabel(frame, text="Cliente:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=4)

        self.customer_combo = ctk.CTkComboBox(frame, variable=self.customer_name_var, width=330, command=self._on_customer_selected)
        self.customer_combo.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=4)

        # Popoliamo la combobox con i clienti
        self._refresh_customer_combo()


        ctk.CTkLabel(frame, text="Indirizzo Cliente:").grid(row=1, column=2, sticky="w", padx=(0, 5), pady=4)
        ctk.CTkEntry(frame, textvariable=self.customer_address_var, width=350).grid(row=1, column=3, sticky="ew", pady=4)

        # Riga 3: Referente (Parroco) e Oggetto
        ctk.CTkLabel(frame, text="Referente/Parroco:").grid(row=2, column=0, sticky="w", padx=(0, 5), pady=4)
        ctk.CTkEntry(frame, textvariable=self.contact_person_var, width=350).grid(row=2, column=1, sticky="ew", padx=(0, 15), pady=4)

        ctk.CTkLabel(frame, text="Oggetto Preventivo:").grid(row=2, column=2, sticky="w", padx=(0, 5), pady=4)
        ctk.CTkEntry(frame, textvariable=self.oggetto_var, width=350).grid(row=2, column=3, sticky="ew", pady=4)

        # Riga 4: Note finali
        ctk.CTkLabel(frame, text="Note a piè pagina:").grid(row=3, column=0, sticky="w", padx=(0, 5), pady=4)
        ctk.CTkEntry(frame, textvariable=self.final_notes_var).grid(row=3, column=1, columnspan=3, sticky="ew", pady=4)

        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

    def _build_form(self) -> None:
        frame_container = ctk.CTkFrame(self.root)
        frame_container.pack(fill="x", padx=12, pady=0)

        ctk.CTkLabel(frame_container, text="Aggiungi / Modifica Articolo", font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")).pack(anchor="w", padx=12, pady=(8,0))

        frame = ctk.CTkFrame(frame_container, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=(0, 12))


        ctk.CTkLabel(frame, text="Descrizione (Cerca in Woo)").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ctk.CTkLabel(frame, text="Prezzo cad. (€)").grid(row=0, column=1, sticky="w", padx=(0, 8), pady=2)
        ctk.CTkLabel(frame, text="Quantità").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=2)
        ctk.CTkLabel(frame, text="IVA %").grid(row=0, column=3, sticky="w", padx=(0, 8), pady=2)

        self.name_var = tk.StringVar()
        self.price_var = tk.StringVar()
        self.qty_var = tk.StringVar()
        self.vat_var = tk.StringVar(value="22")

        # WooCommerce Autocomplete with Entry + Floating Listbox
        self.desc_entry = ctk.CTkEntry(frame, textvariable=self.name_var, width=400)
        self.desc_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=4)

        self.woo_name_map = {}

        # Floating Toplevel for autocomplete (escapes all clipping)
        self.autocomplete_win = tk.Toplevel(self.root)
        self.autocomplete_win.wm_overrideredirect(True)
        self.autocomplete_win.withdraw() # Hidden by default

        self.autocomplete_listbox = tk.Listbox(self.autocomplete_win, height=6, font=("Helvetica", 10))
        self.autocomplete_listbox.pack(fill="both", expand=True)

        self._update_woo_autocomplete()


        def hide_autocomplete(event=None):
            self.autocomplete_win.withdraw()

        def on_desc_key(event):
            if event.keysym in ("Return", "Up", "Down", "Left", "Right", "Escape"):
                if event.keysym == "Escape":
                    hide_autocomplete()
                elif event.keysym == "Return":
                    self.add_item()
                return

            val = self.name_var.get().lower()
            if not val:
                hide_autocomplete()
                return

            filtered = [name for name in self.woo_name_map.keys() if val in name.lower()]

            if filtered:
                self.autocomplete_listbox.delete(0, tk.END)
                for item in filtered[:15]: # Show max 15 items
                    self.autocomplete_listbox.insert(tk.END, item)

                # Position the toplevel window exactly under the entry globally
                x = self.desc_entry.winfo_rootx()
                y = self.desc_entry.winfo_rooty() + self.desc_entry.winfo_height()
                w = self.desc_entry.winfo_width()
                # height roughly calculated as 6 rows * 20px
                self.autocomplete_win.geometry(f"{w}x120+{x}+{y}")
                self.autocomplete_win.deiconify()
                self.autocomplete_win.lift()
            else:
                hide_autocomplete()

        def on_listbox_select(event):
            if not self.autocomplete_listbox.curselection():
                return

            index = self.autocomplete_listbox.curselection()[0]
            val = self.autocomplete_listbox.get(index)

            self.name_var.set(val)
            if val in self.woo_name_map:
                prod = self.woo_name_map[val]
                self.price_var.set(str(prod["price"]))
                self.vat_var.set("0")

            hide_autocomplete()
            self.desc_entry.focus_set()
            # Move cursor to end

            # Since desc_entry is CTkEntry we can use tk entry behind it
            if hasattr(self.desc_entry, "_entry"):
                 self.desc_entry._entry.icursor(tk.END)

        self.desc_entry.bind("<KeyRelease>", on_desc_key)
        self.desc_entry.bind("<FocusOut>", lambda e: self.root.after(200, hide_autocomplete))
        self.autocomplete_listbox.bind("<ButtonRelease-1>", on_listbox_select)



        self.price_entry = ctk.CTkEntry(frame, textvariable=self.price_var, width=120)
        self.price_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=4)

        self.qty_entry = ctk.CTkEntry(frame, textvariable=self.qty_var, width=100)
        self.qty_entry.grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=4)

        self.vat_entry = ctk.CTkEntry(frame, textvariable=self.vat_var, width=80)
        self.vat_entry.grid(row=1, column=3, sticky="ew", padx=(0, 8), pady=4)

        ctk.CTkButton(frame, text="➕ Aggiungi alla lista", command=self.add_item).grid(row=1, column=4, padx=(6, 0), pady=4)

        self.price_entry.bind("<Return>", lambda e: self.add_item())
        self.qty_entry.bind("<Return>", lambda e: self.add_item())
        self.vat_entry.bind("<Return>", lambda e: self.add_item())

        frame.columnconfigure(0, weight=1)



    def _update_woo_autocomplete(self):
        if not hasattr(self, 'desc_entry'):
            return
        self.woo_name_map = {p["name"].strip(): p for p in self.woo_products if p.get("name") and p["name"].strip()}
    def _on_vat_toggle(self) -> None:
        if hasattr(self, 'tree'):
            if self.show_vat_var.get():
                self.tree["displaycolumns"] = ("name", "unit_price", "quantity", "total", "vat", "total_with_vat")
                self.tree.heading("total", text="Importo Tot")
            else:
                self.tree["displaycolumns"] = ("name", "unit_price", "quantity", "total")
                self.tree.heading("total", text="Totale")
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        if self.show_vat_var.get():
            generale = q(sum((item["total_with_vat"] for item in self.items), Decimal("0")))
        else:
            generale = q(sum((item["total"] for item in self.items), Decimal("0")))
        self.summary_var.set(f"Totale Generale: € {format_decimal(generale)}")

    def _build_table(self) -> None:
        frame_container = ctk.CTkFrame(self.root)
        frame_container.pack(fill="both", expand=True, padx=12, pady=8)

        table_header_frame = ctk.CTkFrame(frame_container, fg_color="transparent")
        table_header_frame.pack(fill="x", padx=12, pady=(8, 0))

        ctk.CTkLabel(table_header_frame, text="Articoli Inseriti", font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")).pack(side="left")

        self.show_vat_cb = ctk.CTkCheckBox(
            table_header_frame,
            text="Mostra colonna IVA (in tabella e in stampa)",
            variable=self.show_vat_var,
            command=self._on_vat_toggle
        )
        self.show_vat_cb.pack(side="right")

        frame = ctk.CTkFrame(frame_container, fg_color="transparent")
        # expand=True permette alla tabella di occupare lo spazio rimanente, ma non spingerà fuori i bottoni già pacchettizzati
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("name", "unit_price", "quantity", "total", "vat", "total_with_vat")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)

        self.tree.heading("name", text="Descrizione")
        self.tree.heading("unit_price", text="Prezzo cad.")
        self.tree.heading("quantity", text="Quantità")
        self.tree.heading("total", text="Importo Tot")
        self.tree.heading("vat", text="C.Iva (%)")
        self.tree.heading("total_with_vat", text="Totale")

        self.tree.column("name", width=300, anchor="w", stretch=tk.YES)
        self.tree.column("unit_price", width=100, anchor="e", stretch=tk.NO)
        self.tree.column("quantity", width=80, anchor="center", stretch=tk.NO)
        self.tree.column("total", width=100, anchor="e", stretch=tk.NO)
        self.tree.column("vat", width=80, anchor="center", stretch=tk.NO)
        self.tree.column("total_with_vat", width=100, anchor="e", stretch=tk.NO)

        self._on_vat_toggle()

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_double_click_edit)

    def _on_double_click_edit(self, event) -> None:
        row_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not row_id or not column:
            return

        col_index = int(column[1:]) - 1
        # Editable columns: 0 (name), 1 (unit_price), 2 (quantity), 4 (vat)
        if col_index not in [0, 1, 2, 4]:
            return

        x, y, width, height = self.tree.bbox(row_id, column)

        # Determine justification
        if col_index == 0:
            justify = "left"
        elif col_index == 1:
            justify = "right"
        elif col_index in [2, 4]:
            justify = "center"
        else:
            justify = "left"

        # Use tk.Entry instead of ttk.Entry to avoid clipping
        entry = tk.Entry(self.tree, justify=justify, font=("Helvetica", 10))
        # Add slight padding to height to prevent clipping
        entry.place(x=x, y=y-2, width=width, height=height+4)

        old_val = self.tree.item(row_id, 'values')[col_index]
        entry.insert(0, old_val)
        entry.focus_set()

        def save_edit(evt):
            if not entry.winfo_exists():
                return
            new_val = entry.get()
            entry.destroy()
            if new_val == old_val:
                return

            index = self.tree.index(row_id)
            item = self.items[index]

            try:
                if col_index == 0:
                    item["name"] = new_val
                elif col_index == 1:
                    item["unit_price"] = q(parse_decimal(new_val, "Prezzo cad."))
                elif col_index == 2:
                    item["quantity"] = q(parse_decimal(new_val, "Quantità"))
                elif col_index == 4:
                    item["vat_percent"] = q(parse_decimal(new_val.replace('%', ''), "IVA"))

                # Recalculate
                item["total"] = q(item["unit_price"] * item["quantity"])
                item["total_with_vat"] = q(item["total"] + (item["total"] * item["vat_percent"] / Decimal("100")))

                qty_str = f"{int(item['quantity'])}" if item['quantity'] % 1 == 0 else format_decimal(item['quantity'])

                self.tree.item(row_id, values=(
                    item["name"],
                    format_decimal(item["unit_price"]),
                    qty_str,
                    format_decimal(item["total"]),
                    format_decimal(item["vat_percent"]),
                    format_decimal(item["total_with_vat"]),
                ))
                self._refresh_summary()
                self._save_draft()
            except ValueError as exc:
                messagebox.showerror("Errore di validazione", str(exc))

        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)

    def _build_buttons(self) -> None:
        # Questo frame è pacchettizzato BOTTOM, quindi starà sempre in fondo.
        # fill="x" lo fa occupare tutto lo spazio orizzontale
        frame = ctk.CTkFrame(self.root, fg_color="transparent")
        frame.pack(side="bottom", fill="x", padx=12, pady=12)

        # Sezione di sinistra: Riepilogo e pulsanti tabella
        left_frame = ctk.CTkFrame(frame, fg_color="transparent")
        left_frame.pack(side="left")
        
        self.summary_var = tk.StringVar(value="Totale Generale: € 0,00")
        ctk.CTkLabel(left_frame, textvariable=self.summary_var, font=ctk.CTkFont(family="Helvetica", size=14, weight="bold")).pack(side="left", padx=(0, 15))
        

        ctk.CTkButton(left_frame, text="❌ Rimuovi", command=self.remove_selected, width=100, fg_color="#d32f2f", hover_color="#b71c1c").pack(side="left", padx=4)

        # Sezione di destra: Azioni progetto
        right_frame = ctk.CTkFrame(frame, fg_color="transparent")
        right_frame.pack(side="right")

        ctk.CTkButton(right_frame, text="🆕 Svuota Tutto", command=self.new_project, width=120).pack(side="left", padx=4)
        ctk.CTkButton(right_frame, text="🗄️ Archivio", command=self.show_archive_window, width=100).pack(side="left", padx=4)
        ctk.CTkButton(right_frame, text="💾 Esporta", command=self.save_project, width=100).pack(side="left", padx=4)
        ctk.CTkButton(right_frame, text="📂 Importa", command=self.load_project, width=100).pack(side="left", padx=4)
        ctk.CTkButton(right_frame, text="👁️ Anteprima", command=self.preview_pdf, width=110).pack(side="left", padx=4)
        ctk.CTkButton(right_frame, text="📄 GENERA PDF", command=self.generate_pdf, fg_color="#388e3c", hover_color="#2e7d32", width=140).pack(side="left", padx=(15, 0))

    def _refresh_customer_combo(self):
        customers = storage.load_customers()
        self.customer_combo.configure(values=sorted(list(customers.keys())))

    def _on_customer_selected(self, event=None):
        selected = self.customer_name_var.get()
        if not selected: return
        customer_data = storage.get_customer(selected)
        if customer_data:
            self.customer_address_var.set(customer_data.get("address", ""))
            self.contact_person_var.set(customer_data.get("contact", ""))

    def _validate_fields(self):
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("Il campo 'Descrizione' è obbligatorio.")

        unit_price = parse_decimal(self.price_var.get(), "Prezzo cad.")
        quantity = parse_decimal(self.qty_var.get(), "Quantità")
        vat_percent = parse_decimal(self.vat_var.get(), "IVA %")

        if unit_price < 0 or quantity <= 0 or vat_percent < 0:
            raise ValueError("Valori numerici non validi (negativi o a zero).")

        total = q(unit_price * quantity)
        total_with_vat = q(total * (Decimal("1") + (vat_percent / Decimal("100"))))

        return {
            "name": name,
            "unit_price": q(unit_price),
            "quantity": q(quantity),
            "vat_percent": q(vat_percent),
            "total": total,
            "total_with_vat": total_with_vat,
        }

    def add_item(self) -> None:
        try:
            item = self._validate_fields()
        except ValueError as exc:
            messagebox.showerror("Errore", str(exc))
            return

        self.items.append(item)
        self._insert_tree_row(item)
        self._refresh_summary()
        self._save_draft()
        
        self.name_var.set("")
        self.price_var.set("")
        self.qty_var.set("")
        self.vat_var.set("22")
        if hasattr(self, 'autocomplete_win'):
            self.autocomplete_win.withdraw()
        
    def _insert_tree_row(self, item):
        qty_str = f"{item['quantity']:,.0f}" if item['quantity'] % 1 == 0 else format_decimal(item['quantity'])
        self.tree.insert(
            "", "end",
            values=(
                item["name"],
                format_decimal(item["unit_price"]),
                qty_str,
                format_decimal(item["total"]),
                format_decimal(item["vat_percent"]),
                format_decimal(item["total_with_vat"]),
            )
        )

    def remove_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        for row_id in selected:
            index = self.tree.index(row_id)
            self.tree.delete(row_id)
            if 0 <= index < len(self.items):
                self.items.pop(index)
        self._refresh_summary()
        self._save_draft()

    def _refresh_summary(self) -> None:
        generale = q(sum((item["total_with_vat"] for item in self.items), Decimal("0")))
        self.summary_var.set(f"Totale Generale: € {format_decimal(generale)}")

    def new_project(self) -> None:
        if not messagebox.askyesno("Nuovo", "Svuotare tutti i dati del cliente e della tabella?"):
            return
        self.quote_date_var.set(str(date.today().strftime("%d/%m/%Y")))
        self.customer_name_var.set("")
        self.customer_address_var.set("")
        self.contact_person_var.set("")
        self.oggetto_var.set("")
        self.final_notes_var.set("")
        self.show_vat_var.set(True)
        self._on_vat_toggle()
        self.items.clear()
        self.tree.delete(*self.tree.get_children())
        self._refresh_summary()
        self._delete_draft()

    def _serialize_items(self):
        return [{k: str(v) if isinstance(v, Decimal) else v for k, v in i.items()} for i in self.items]

    def save_project(self) -> None:
        # Salva o aggiorna in anagrafica
        storage.save_customer(
            self.customer_name_var.get(),
            self.customer_address_var.get(),
            self.contact_person_var.get()
        )
        self._refresh_customer_combo()

        path = filedialog.asksaveasfilename(defaultextension=".pquote", filetypes=[("Progetto Preventivatore", "*.pquote")])
        if not path: return
        payload = {
            "customer": {
                "name": self.customer_name_var.get(),
                "address": self.customer_address_var.get(),
                "contact": self.contact_person_var.get(),
                "oggetto": self.oggetto_var.get(),
                "quote_date": self.quote_date_var.get(),
                "notes": self.final_notes_var.get(),
            },
            "show_vat": self.show_vat_var.get(),
            "items": self._serialize_items()
        }
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)


    def show_archive_window(self):
        archive_win = ctk.CTkToplevel(self.root)
        archive_win.title("Archivio Preventivi Locali")
        archive_win.geometry("600x400")
        archive_win.transient(self.root)
        archive_win.grab_set()

        columns = ("filename", "date")
        tree = ttk.Treeview(archive_win, columns=columns, show="headings")
        tree.heading("filename", text="Nome File")
        tree.heading("date", text="Data Creazione")
        tree.column("filename", width=400, anchor="w")
        tree.column("date", width=150, anchor="center")

        import datetime
        quotes = storage.list_local_quotes()
        for q in quotes:
            dt_str = datetime.datetime.fromtimestamp(q["mtime"]).strftime("%d/%m/%Y %H:%M")
            tree.insert("", "end", values=(q["filename"], dt_str), tags=(q["filepath"],))

        tree.pack(fill="both", expand=True, padx=10, pady=10)

        def on_double_click(event):
            selected = tree.selection()
            if not selected: return
            filepath = tree.item(selected[0], "tags")[0]
            self._load_from_filepath(filepath)
            archive_win.destroy()

        tree.bind("<Double-1>", on_double_click)

        ctk.CTkLabel(archive_win, text="Doppio clic su un preventivo per caricarlo.").pack(pady=(0,10))

    def _load_from_filepath(self, filepath: str):
        payload = storage.load_local_quote(filepath)
        if not payload:
            messagebox.showerror("Errore", "Impossibile caricare il file.")
            return

        cust = payload.get("customer", {})
        self.customer_name_var.set(cust.get("name", ""))
        self.customer_address_var.set(cust.get("address", ""))
        self.contact_person_var.set(cust.get("contact", ""))
        self.oggetto_var.set(cust.get("oggetto", ""))
        self.quote_date_var.set(cust.get("quote_date", str(datetime.date.today().strftime("%d/%m/%Y"))))
        self.final_notes_var.set(cust.get("notes", ""))
        self.show_vat_var.set(bool(payload.get("show_vat", True)))
        self._on_vat_toggle()

        self.items = []
        self.tree.delete(*self.tree.get_children())
        for item in payload.get("items", []):
            i = {
                "name": str(item["name"]),
                "unit_price": q(Decimal(str(item["unit_price"]))),
                "quantity": q(Decimal(str(item["quantity"]))),
                "vat_percent": q(Decimal(str(item["vat_percent"]))),
                "total": q(Decimal(str(item["total"]))),
                "total_with_vat": q(Decimal(str(item["total_with_vat"]))),
            }
            self.items.append(i)
            self._insert_tree_row(i)
        self._refresh_summary()

    def load_project(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Progetto Preventivatore", "*.pquote")])
        if not path: return
        with open(path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        
        cust = payload.get("customer", {})
        self.customer_name_var.set(cust.get("name", ""))
        self.customer_address_var.set(cust.get("address", ""))
        self.contact_person_var.set(cust.get("contact", ""))
        self.oggetto_var.set(cust.get("oggetto", ""))
        self.quote_date_var.set(cust.get("quote_date", str(date.today().strftime("%d/%m/%Y"))))
        self.final_notes_var.set(cust.get("notes", ""))
        self.show_vat_var.set(bool(payload.get("show_vat", True)))
        self._on_vat_toggle()

        self.items = []
        self.tree.delete(*self.tree.get_children())
        for item in payload.get("items", []):
            i = {
                "name": str(item["name"]),
                "unit_price": q(Decimal(str(item["unit_price"]))),
                "quantity": q(Decimal(str(item["quantity"]))),
                "vat_percent": q(Decimal(str(item["vat_percent"]))),
                "total": q(Decimal(str(item["total"]))),
                "total_with_vat": q(Decimal(str(item["total_with_vat"]))),
            }
            self.items.append(i)
            self._insert_tree_row(i)
        self._refresh_summary()


    def _get_doc_data(self) -> dict:
        return {
            "company_name": self.settings.get("company_name", ""),
            "company_address": self.settings.get("company_address", ""),
            "piva": self.settings.get("piva", ""),
            "email": self.settings.get("email", ""),
            "phone": self.settings.get("phone", ""),
            "logo_path": self.settings.get("logo_path", ""),
            
            "quote_number": self.quote_number_var.get(),
            "quote_date": self.quote_date_var.get(),
            "customer_name": self.customer_name_var.get(),
            "customer_address": self.customer_address_var.get(),
            "contact_person": self.contact_person_var.get(),
            "oggetto": self.oggetto_var.get(),
            "final_notes": self.final_notes_var.get(),
            "show_vat": self.show_vat_var.get(),
        }

    def preview_pdf(self) -> None:
        if not self.items:
            messagebox.showwarning("Errore", "Aggiungi articoli prima di generare l'anteprima del PDF.")
            return


        try:
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            generate_quote_pdf(self.items, self._get_doc_data(), temp_path)

            try:
                if platform.system() == "Windows":
                    os.startfile(temp_path)
                elif platform.system() == "Darwin":
                    subprocess.call(["open", temp_path])
                else:
                    subprocess.call(["xdg-open", temp_path])
            except Exception as e:
                messagebox.showerror("Errore Apertura PDF", f"Impossibile aprire il file PDF.\nErrore: {str(e)}")
        except Exception as exc:
            messagebox.showerror("Errore Anteprima", str(exc))

    def generate_pdf(self) -> None:

        if not self.items:
            messagebox.showwarning("Errore", "Aggiungi articoli prima di generare il PDF.")
            return

        # Salva o aggiorna in anagrafica
        storage.save_customer(
            self.customer_name_var.get(),
            self.customer_address_var.get(),
            self.contact_person_var.get()
        )
        self._refresh_customer_combo()

        out_name = f"Preventivo_{self.quote_number_var.get()}_{self.customer_name_var.get().replace(' ','_')}.pdf"
        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=out_name, filetypes=[("PDF", "*.pdf")])
        if not file_path: return

        try:
            generate_quote_pdf(self.items, self._get_doc_data(), file_path)

            # Salva una copia nel database locale
            payload = {
                "customer": {
                    "name": self.customer_name_var.get(),
                    "address": self.customer_address_var.get(),
                    "contact": self.contact_person_var.get(),
                    "oggetto": self.oggetto_var.get(),
                    "quote_date": self.quote_date_var.get(),
                    "notes": self.final_notes_var.get(),
                },
                "items": self._serialize_items()
            }
            storage.save_local_quote(payload, self.quote_number_var.get(), self.customer_name_var.get())
            self._delete_draft()

            messagebox.showinfo("Fatto!", f"PDF generato:\n{file_path}")
            self._delete_draft()
            # PDF PREVIEW
            try:
                if platform.system() == "Windows":
                    os.startfile(file_path)
                elif platform.system() == "Darwin":
                    subprocess.call(["open", file_path])
                else:
                    subprocess.call(["xdg-open", file_path])
            except Exception as e:
                print(f"Preview error: {e}")

        except Exception as exc:
            messagebox.showerror("Errore PDF", str(exc))

def main() -> None:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()

    # Configure ttk style for Treeview to match CustomTkinter
    style = ttk.Style(root)
    style.theme_use("default")

    bg_color = root._apply_appearance_mode(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
    text_color = root._apply_appearance_mode(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
    selected_color = root._apply_appearance_mode(ctk.ThemeManager.theme["CTkButton"]["fg_color"])

    style.configure("Treeview",
                    background=bg_color,
                    foreground=text_color,
                    rowheight=25,
                    fieldbackground=bg_color,
                    borderwidth=0)
    style.map('Treeview', background=[('selected', selected_color)])
    style.configure("Treeview.Heading",
                    background=bg_color,
                    foreground=text_color,
                    relief="flat",
                    font=("Helvetica", 10, "bold"))
    style.map("Treeview.Heading",
              background=[('active', selected_color)])

    app = PreventivoApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()