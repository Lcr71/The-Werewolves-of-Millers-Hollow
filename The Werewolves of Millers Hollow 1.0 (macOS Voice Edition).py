import random
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox
from functools import partial

# ============================================================
# macOS VOICE ENGINE
# ============================================================

RATE_EN = "175"
RATE_ZH = "170"
_voice_cache = None
_current_process = None
_process_lock = threading.Lock()


def stop_current_speech():
    global _current_process
    with _process_lock:
        if _current_process and _current_process.poll() is None:
            try:
                _current_process.kill()
            except Exception:
                pass
            _current_process = None


def get_macos_voices():
    try:
        result = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, check=False
        )
        voices = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                lang_idx = -1
                for idx, part in enumerate(parts):
                    if "_" in part and len(part) == 5:
                        lang_idx = idx
                        break
                if lang_idx != -1:
                    voice_name = " ".join(parts[:lang_idx])
                    lang_code = parts[lang_idx]
                    voices.append(
                        {"name": voice_name, "lang": lang_code, "raw": line.lower()}
                    )
        return voices
    except Exception:
        return []


def find_voice(preferred, lang_codes):
    voices = get_macos_voices()
    for pref in preferred:
        for v in voices:
            if pref.lower() in v["name"].lower():
                return v["name"]
    for lang in lang_codes:
        for v in voices:
            if lang.lower() in v["lang"].lower():
                return v["name"]
    for v in voices:
        if "chinese" in v["raw"] or "mandarin" in v["raw"]:
            return v["name"]
    return None


def get_voices():
    global _voice_cache
    if _voice_cache is not None:
        return _voice_cache
    english = find_voice(["Samantha", "Alex", "Victoria"], ["en_US", "English"])
    chinese = find_voice(
        ["TingTing", "Li-Mu", "Mei-Jia", "Tian-Tian"], ["zh_CN", "zh_TW"]
    )
    _voice_cache = {"english": english, "chinese": chinese}
    return _voice_cache


def say_one(text, voice, rate):
    global _current_process
    if not voice:
        print("No voice:", text)
        return
    try:
        proc = subprocess.Popen(["say", "-v", voice, "-r", rate, text])
        with _process_lock:
            _current_process = proc
        proc.wait()
    except Exception as e:
        print("TTS error:", e)


def speak(en="", zh="", enable_zh=True, on_finished=None):
    """Safely executes TTS without hardcoding global root references"""
    voices = get_voices()
    stop_current_speech()

    def run_speech():
        if en and voices["english"]:
            say_one(en, voices["english"], RATE_EN)
        if enable_zh and zh and voices["chinese"]:
            say_one(zh, voices["chinese"], RATE_ZH)
        if on_finished:
            try:
                on_finished()
            except Exception as e:
                print("Speech callback error:", e)

    threading.Thread(target=run_speech, daemon=True).start()


# ============================================================
# GAME DEFINITIONS
# ============================================================

ALL_ROLES = {
    "Werewolf": {"name_en": "Werewolf", "name_zh": "狼人", "emoji": "🐺", "side": "wolf"},
    "Seer": {"name_en": "Seer", "name_zh": "预言家", "emoji": "🔮", "side": "god"},
    "Witch": {"name_en": "Witch", "name_zh": "女巫", "emoji": "🧪", "side": "god"},
    "Hunter": {"name_en": "Hunter", "name_zh": "猎人", "emoji": "🏹", "side": "god"},
    "Guard": {"name_en": "Guard", "name_zh": "守卫", "emoji": "🛡️", "side": "god"},
    "Knight": {"name_en": "Knight", "name_zh": "骑士", "emoji": "⚔️", "side": "god"},
    "Idiot": {"name_en": "Idiot", "name_zh": "白痴", "emoji": "🤡", "side": "god"},
    "Villager": {"name_en": "Villager", "name_zh": "平民", "emoji": "👤", "side": "villager"},
}


class WerewolfJudge:

    def __init__(self, root):
        self.root = root
        self.root.title("🐺 Werewolf AI Judge")
        self.root.geometry("1000x800")
        self.root.minsize(900, 700)

        # Config Settings
        self.lang_mode = "EN"  # Options: "EN" or "EN_ZH"
        self.player_count = 8

        # Game State
        self.players = []
        self.roles = []
        self.alive = []
        self.idiot_revealed = []
        self.night = 0
        self.actions = {}

        self.sheriff = None
        self.sheriff_elected = False

        self.witch_heal_used = False
        self.witch_poison_used = False
        self.last_guarded = None
        self.knight_ability_used = False

        self.pending_hunter_deaths = []
        self.pending_sheriff_deaths = []

        self.build_setup_config()

    def txt(self, en, zh=""):
        """Returns text string based on selected language mode"""
        if self.lang_mode == "EN_ZH" and zh:
            return f"{en} / {zh}"
        return en

    def speak_game(self, en="", zh="", on_finished=None):
        enable_zh = (self.lang_mode == "EN_ZH")
        # Ensure UI callback thread safety using self.root.after
        def safe_callback():
            if on_finished:
                self.root.after(0, on_finished)

        speak(en=en, zh=zh, enable_zh=enable_zh, on_finished=safe_callback if on_finished else None)

    def get_role_display(self, role_key):
        info = ALL_ROLES[role_key]
        if self.lang_mode == "EN_ZH":
            return f"{info['emoji']} {info['name_en']} / {info['name_zh']}"
        return f"{info['emoji']} {info['name_en']}"

    def clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def title(self, text):
        tk.Label(self.root, text=text, font=("Arial", 24, "bold"), wraplength=850).pack(pady=12)

    def subtitle(self, text):
        tk.Label(self.root, text=text, font=("Arial", 14), wraplength=850).pack(pady=3)

    def button(
        self,
        parent,
        text,
        command,
        width=24,
        height=2,
        bg=None,
        fg=None,
        state=tk.NORMAL,
    ):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            font=("Arial", 12),
            state=state,
        )
        if bg:
            btn.configure(bg=bg)
        if fg:
            btn.configure(fg=fg)
        return btn

    def player_buttons(self, command, filter_alive=True, exclude_ids=None):
        if exclude_ids is None:
            exclude_ids = []
        frame = tk.Frame(self.root)
        frame.pack(pady=10)

        row, col = 0, 0
        max_cols = 4 if self.player_count <= 10 else 5

        for i in range(self.player_count):
            if filter_alive and not self.alive[i]:
                continue
            if i in exclude_ids:
                continue

            is_sheriff = i == self.sheriff
            badge = "👮 " if is_sheriff else ""
            idiot_flag = "🤡" if self.idiot_revealed[i] else ""
            btn_text = f"{badge}{idiot_flag}{i + 1}. {self.players[i]}"

            self.button(
                frame, btn_text, partial(command, i), width=16, height=2
            ).grid(row=row, column=col, padx=5, pady=5)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    # -------------------------
    # CONFIG & SETUP
    # -------------------------

    def build_setup_config(self):
        self.clear()
        self.title("⚙️ Game Setup")

        # Language Selector
        lang_frame = tk.LabelFrame(
            self.root, text="Language / 语言设置", font=("Arial", 11, "bold"), padx=10, pady=5
        )
        lang_frame.pack(pady=5)

        self.lang_var = tk.StringVar(value=self.lang_mode)
        tk.Radiobutton(
            lang_frame, text="English Only", variable=self.lang_var, value="EN", font=("Arial", 11)
        ).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(
            lang_frame, text="English + 中文", variable=self.lang_var, value="EN_ZH", font=("Arial", 11)
        ).pack(side=tk.LEFT, padx=10)

        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10)

        tk.Label(
            top_frame, text="Number of Players (6-18):", font=("Arial", 14)
        ).grid(row=0, column=0, padx=5)

        self.cnt_var = tk.IntVar(value=self.player_count)
        spin = tk.Spinbox(
            top_frame,
            from_=6,
            to=18,
            textvariable=self.cnt_var,
            width=5,
            font=("Arial", 14),
            command=self.update_role_defaults,
        )
        spin.grid(row=0, column=1, padx=5)

        self.role_inputs = {}
        role_frame = tk.LabelFrame(
            self.root,
            text="Role Allocation",
            font=("Arial", 12, "bold"),
            padx=10,
            pady=10,
        )
        role_frame.pack(pady=10, fill="x", padx=20)

        default_counts = {
            "Werewolf": 3,
            "Seer": 1,
            "Witch": 1,
            "Hunter": 1,
            "Guard": 0,
            "Knight": 0,
            "Idiot": 0,
            "Villager": 2,
        }

        r, c = 0, 0
        for key, info in ALL_ROLES.items():
            sub = tk.Frame(role_frame)
            sub.grid(row=r, column=c, padx=10, pady=5, sticky="w")
            tk.Label(
                sub,
                text=f"{info['emoji']} {key}:",
                font=("Arial", 11),
                width=10,
                anchor="e",
            ).pack(side=tk.LEFT)
            var = tk.IntVar(value=default_counts[key])
            sp = tk.Spinbox(
                sub, from_=0, to=10, textvariable=var, width=3, font=("Arial", 11)
            )
            sp.pack(side=tk.LEFT, padx=2)
            self.role_inputs[key] = var

            c += 1
            if c >= 4:
                c = 0
                r += 1

        self.button(
            self.root,
            "➡️ Next: Player Names",
            self.build_player_names,
            width=28,
        ).pack(pady=15)

    def update_role_defaults(self):
        cnt = self.cnt_var.get()
        wolves = max(2, cnt // 3)
        gods = min(4, cnt // 3)
        villagers = cnt - wolves - gods

        self.role_inputs["Werewolf"].set(wolves)
        self.role_inputs["Villager"].set(villagers)

    def build_player_names(self):
        self.lang_mode = self.lang_var.get()
        total_roles = sum(v.get() for v in self.role_inputs.values())
        self.player_count = self.cnt_var.get()

        if total_roles != self.player_count:
            messagebox.showerror(
                "Config Error",
                f"Total selected roles ({total_roles}) does not match player count ({self.player_count})!",
            )
            return

        self.clear()
        self.title(self.txt("👤 Player Names", "玩家姓名"))

        canvas = tk.Canvas(self.root, height=450)
        scrollbar = tk.Scrollbar(
            self.root, orient="vertical", command=canvas.yview
        )
        scroll_frame = tk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        self.name_entries = []
        for i in range(self.player_count):
            row_f = tk.Frame(scroll_frame)
            row_f.pack(pady=3)
            tk.Label(
                row_f,
                text=f"Player {i + 1} Name:",
                font=("Arial", 11),
                width=14,
                anchor="e",
            ).pack(side=tk.LEFT)
            e = tk.Entry(row_f, width=20, font=("Arial", 11))
            e.insert(0, f"Player {i + 1}")
            e.pack(side=tk.LEFT, padx=5)
            self.name_entries.append(e)

        canvas.pack(side=tk.TOP, fill="both", expand=True, padx=20)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        self.button(
            self.root, self.txt("🎲 Deal Roles", "发牌"), self.deal_roles, width=28
        ).pack(pady=15)

    def deal_roles(self):
        self.players = [
            e.get().strip() or f"Player {i + 1}"
            for i, e in enumerate(self.name_entries)
        ]

        role_pool = []
        for key, var in self.role_inputs.items():
            role_pool.extend([key] * var.get())

        random.shuffle(role_pool)
        self.roles = role_pool
        self.alive = [True] * self.player_count
        self.idiot_revealed = [False] * self.player_count

        self.night = 0
        self.sheriff = None
        self.sheriff_elected = False

        self.witch_heal_used = False
        self.witch_poison_used = False
        self.last_guarded = None
        self.knight_ability_used = False

        self.pending_hunter_deaths = []
        self.pending_sheriff_deaths = []

        self.show_roles()

    def show_roles(self):
        self.clear()
        self.title(self.txt("🎴 Check Role Cards", "身份牌查看"))
        self.subtitle(self.txt("Click on your name to privately reveal your role.", "点击姓名查看身份，然后关闭。"))

        frame = tk.Frame(self.root)
        frame.pack(pady=15)

        max_cols = 4 if self.player_count <= 10 else 5
        for i, name in enumerate(self.players):
            self.button(
                frame,
                f"👤 {name}\nPlayer {i + 1}",
                partial(self.show_role, i),
                width=16,
                height=3,
            ).grid(
                row=i // max_cols, column=i % max_cols, padx=6, pady=6
            )

        self.button(
            self.root, self.txt("🌙 Start Game", "开始游戏"), self.start_night, width=25
        ).pack(pady=15)

    def show_role(self, i):
        role_key = self.roles[i]
        display = self.get_role_display(role_key)
        messagebox.showinfo(
            self.players[i],
            f"{display}\n\n{self.txt('Remember your role and close this window.', '记住身份并关闭本窗口。')}",
        )

    # -------------------------
    # TRANSITIONS & FAKE WAITING
    # -------------------------

    def transition(self, emoji, title, en, zh, callback):
        self.clear()
        self.title(f"{emoji} {title}")
        self.subtitle(self.txt(en, zh))
        tk.Label(
            self.root,
            text="🔊 Speaking prompts...",
            font=("Arial", 14, "bold"),
            fg="#2b5c8f",
        ).pack(pady=25)
        self.speak_game(en, zh, on_finished=callback)

    def action_complete(self, emoji, title, en, zh, callback):
        self.clear()
        self.title(f"✅ {emoji} {title}")
        self.subtitle(self.txt(en, zh))

        def on_click():
            stop_current_speech()
            callback()

        self.button(
            self.root,
            self.txt("✅ ACTION COMPLETE", "完成"),
            on_click,
            width=30,
            height=3,
        ).pack(pady=35)
        self.speak_game(en, zh)

    def simulate_dead_role_action(self, emoji, title, en, zh, after_callback):
        self.clear()
        self.title(f"{emoji} {title}")
        self.subtitle(self.txt(en, zh))
        tk.Label(
            self.root,
            text="⏳ Waiting for player action...",
            font=("Arial", 14, "bold"),
            fg="#d35400",
        ).pack(pady=25)

        def run_fake_delay():
            fake_delay = random.uniform(3.0, 6.0)
            time.sleep(fake_delay)
            self.root.after(0, after_callback)

        self.speak_game(en, zh, on_finished=lambda: threading.Thread(target=run_fake_delay, daemon=True).start())

    # -------------------------
    # NIGHT PHASE FLOW
    # -------------------------

    def start_night(self):
        # Reset actions dictionary every night to prevent residual state bugs
        self.actions = {}
        self.transition(
            "🌙",
            f"NIGHT {self.night + 1}",
            "Everyone, close your eyes.",
            "天黑请闭眼。",
            self.guard_phase,
        )

    # 1. Guard Phase
    def guard_phase(self):
        if "Guard" not in self.roles:
            self.werewolf_phase()
            return

        guard = next(
            (
                i
                for i in range(self.player_count)
                if self.alive[i] and self.roles[i] == "Guard"
            ),
            None,
        )

        if guard is None:
            self.simulate_dead_role_action(
                "🛡️",
                "GUARD",
                "Guard, wake up. Choose a target to protect.",
                "守卫请睁眼，请选择守护的目标。",
                self.after_guard,
            )
            return

        self.clear()
        self.title("🛡️ GUARD")
        self.subtitle(self.txt("Guard, wake up. Choose a player to protect tonight.", "守卫请睁眼，选择守护的目标（不可连守）。"))

        frame = tk.Frame(self.root)
        frame.pack(pady=12)

        exclude = [self.last_guarded] if self.last_guarded is not None else []
        self.player_buttons(self.choose_guard, exclude_ids=exclude)

        self.button(
            self.root, self.txt("⏭️ SKIP", "空守"), self.skip_guard, width=22
        ).pack(pady=10)
        self.speak_game("Guard, wake up. Choose a target to protect.", "守卫请睁眼，请选择守护的目标。")

    def choose_guard(self, target):
        self.actions["guard"] = target
        self.last_guarded = target
        self.action_complete(
            "🛡️",
            "Guard Action Complete",
            "Target protected.",
            "守护完成。",
            self.after_guard,
        )

    def skip_guard(self):
        self.actions["guard"] = None
        self.last_guarded = None
        self.action_complete(
            "🛡️",
            "Guard Action Complete",
            "Guard chose to skip.",
            "守卫选择空守。",
            self.after_guard,
        )

    def after_guard(self):
        self.transition(
            "🌙",
            "NEXT ROLE",
            "Guard, close your eyes.",
            "守卫请闭眼。",
            self.werewolf_phase,
        )

    # 2. Werewolf Phase
    def werewolf_phase(self):
        if "Werewolf" not in self.roles:
            self.witch_phase()
            return

        wolves = [
            i
            for i in range(self.player_count)
            if self.alive[i] and self.roles[i] == "Werewolf"
        ]
        if not wolves:
            self.simulate_dead_role_action(
                "🐺",
                "WEREWOLVES",
                "Werewolves, wake up. Choose a target to attack.",
                "狼人请睁眼。请选择今晚袭击的目标。",
                self.after_wolves,
            )
            return

        self.clear()
        self.title("🐺 WEREWOLVES")
        self.subtitle(self.txt("Werewolves, wake up. Choose a target to attack tonight.", "狼人请睁眼，选择今晚袭击的目标。"))

        frame = tk.Frame(self.root)
        frame.pack(pady=10)

        row, col = 0, 0
        for i in range(self.player_count):
            if not self.alive[i]:
                continue
            is_wolf = self.roles[i] == "Werewolf"
            btn_text = (
                f"🐺 {i + 1}. {self.players[i]}\n[{self.txt('Teammate', '队友')}]"
                if is_wolf
                else f"👤 {i + 1}\n{self.players[i]}"
            )

            self.button(
                frame,
                btn_text,
                partial(self.choose_wolf, i),
                width=16,
                height=2,
                fg="red" if is_wolf else None,
            ).grid(row=row, column=col, padx=5, pady=5)
            col += 1
            if col >= 4:
                col = 0
                row += 1

        self.speak_game(
            "Werewolves, wake up. Choose a target to attack.",
            "狼人请睁眼。请选择今晚袭击的目标。",
        )

    def choose_wolf(self, target):
        self.actions["wolf"] = target
        self.action_complete(
            "🐺",
            "Werewolf Action Complete",
            "Attack target selected.",
            "袭击目标已选择。",
            self.after_wolves,
        )

    def after_wolves(self):
        self.transition(
            "🌙",
            "NEXT ROLE",
            "Werewolves, close your eyes.",
            "狼人请闭眼。",
            self.witch_phase,
        )

    # 3. Witch Phase
    def witch_phase(self):
        if "Witch" not in self.roles:
            self.seer_phase()
            return

        witch = next(
            (
                i
                for i in range(self.player_count)
                if self.alive[i] and self.roles[i] == "Witch"
            ),
            None,
        )
        if witch is None:
            self.simulate_dead_role_action(
                "🧪",
                "WITCH",
                "Witch, wake up. Decide whether to use a potion.",
                "女巫请睁眼。请决定是否使用药水。",
                self.after_witch,
            )
            return

        target = self.actions.get("wolf")
        self.clear()
        self.title("🧪 WITCH")
        self.subtitle(self.txt("Witch, wake up.", "女巫请睁眼。"))

        # Rule Fix: Witch can ONLY heal herself on Night 1 (self.night == 0).
        # On subsequent nights, she can only heal other players.
        can_heal_self = (self.night == 0) or (target != witch)

        if target is not None and not self.witch_heal_used:
            target_msg = f"Target attacked tonight: Player {target + 1} ({self.players[target]})"
            if self.lang_mode == "EN_ZH":
                target_msg += f"\n今晚被袭击目标：Player {target + 1} ({self.players[target]})"

            tk.Label(
                self.root,
                text=f"🐺 {target_msg}",
                font=("Arial", 15, "bold"),
                fg="#c0392b",
                wraplength=850,
            ).pack(pady=10)

        frame = tk.Frame(self.root)
        frame.pack(pady=10)

        if target is not None and not self.witch_heal_used and can_heal_self:
            self.button(
                frame, self.txt("💚 Use Antidote", "使用解药"), self.witch_heal, width=24
            ).pack(pady=4)

        if not self.witch_poison_used:
            self.button(
                frame,
                self.txt("☠️ Use Poison", "使用毒药"),
                lambda: self.witch_poison_start(witch),
                width=24,
            ).pack(pady=4)

        self.button(
            frame, self.txt("⏭️ SKIP", "不使用"), self.witch_skip, width=24
        ).pack(pady=4)
        self.speak_game("Witch, wake up. Decide whether to use a potion.", "女巫请睁眼。请决定是否使用药水。")

    def witch_heal(self):
        self.witch_heal_used = True
        self.actions["heal"] = True
        self.action_complete(
            "🧪",
            "Antidote Used",
            "Healing applied.",
            "解药已生效。",
            self.after_witch,
        )

    def witch_poison_start(self, witch_id):
        self.clear()
        self.title("☠️ POISON")
        self.subtitle(self.txt("Select a player to poison (Cannot poison yourself).", "选择一名玩家使用毒药（不可毒自己）。"))
        self.player_buttons(self.witch_poison_choose, exclude_ids=[witch_id])

    def witch_poison_choose(self, target):
        self.witch_poison_used = True
        self.actions["poison"] = target
        self.action_complete(
            "☠️",
            "Poison Used",
            "Poison applied.",
            "毒药已生效。",
            self.after_witch,
        )

    def witch_skip(self):
        self.action_complete(
            "🧪",
            "Witch Action Complete",
            "Skipped potion use.",
            "未选择使用药水。",
            self.after_witch,
        )

    def after_witch(self):
        self.transition(
            "🌙",
            "NEXT ROLE",
            "Witch, close your eyes.",
            "女巫请闭眼。",
            self.seer_phase,
        )

    # 4. Seer Phase
    def seer_phase(self):
        if "Seer" not in self.roles:
            self.finish_night()
            return

        seer = next(
            (
                i
                for i in range(self.player_count)
                if self.alive[i] and self.roles[i] == "Seer"
            ),
            None,
        )
        if seer is None:
            self.simulate_dead_role_action(
                "🔮",
                "SEER",
                "Seer, wake up. Choose a player to check.",
                "预言家请睁眼，请选择查验目标。",
                self.after_seer,
            )
            return

        self.clear()
        self.title("🔮 SEER")
        self.subtitle(self.txt("Seer, wake up. Choose a player to check.", "预言家请睁眼，选择查验目标。"))
        self.player_buttons(self.choose_seer, exclude_ids=[seer])
        self.speak_game("Seer, wake up. Choose a player to check.", "预言家请睁眼，请选择查验目标。")

    def choose_seer(self, target):
        is_wolf = self.roles[target] == "Werewolf"
        res = "🐺 Bad Guy (Werewolf)" if is_wolf else "😇 Good Guy"
        messagebox.showinfo(
            "🔮 Inspection Result", f"Player {target + 1} ({self.players[target]})\n\nAlignment: {res}"
        )
        self.action_complete(
            "🔮",
            "Seer Action Complete",
            "Inspection complete.",
            "查验完毕。",
            self.after_seer,
        )

    def after_seer(self):
        self.transition(
            "🌙",
            "NIGHT ENDS",
            "Seer, close your eyes. Everyone keep your eyes closed.",
            "预言家请闭眼。所有玩家继续闭眼。",
            self.finish_night,
        )

    # -------------------------
    # NIGHT RESULT & CALCULATIONS
    # -------------------------

    def finish_night(self):
        wolf_target = self.actions.get("wolf")
        guarded_target = self.actions.get("guard")
        healed = self.actions.get("heal", False)
        poison_target = self.actions.get("poison")

        night_dead = set()

        if wolf_target is not None:
            is_guarded = wolf_target == guarded_target
            if is_guarded and healed:
                night_dead.add(wolf_target)
            elif is_guarded or healed:
                pass
            else:
                night_dead.add(wolf_target)

        if poison_target is not None:
            night_dead.add(poison_target)

        dead_list = list(night_dead)
        for p in dead_list:
            self.alive[p] = False
            if self.roles[p] == "Hunter" and p != poison_target:
                self.pending_hunter_deaths.append(p)
            if p == self.sheriff:
                self.pending_sheriff_deaths.append(p)

        winner = self.check_winner()
        if winner:
            self.game_over(winner)
            return

        self.process_death_cascade(next_phase=lambda: self.day_start(dead_list))

    def process_death_cascade(self, next_phase):
        if self.pending_hunter_deaths:
            hunter_idx = self.pending_hunter_deaths.pop(0)
            self.hunter_shoot_ui(hunter_idx, next_phase)
            return

        if self.pending_sheriff_deaths:
            sheriff_idx = self.pending_sheriff_deaths.pop(0)
            self.sheriff_badge_transfer_ui(sheriff_idx, next_phase)
            return

        next_phase()

    def hunter_shoot_ui(self, hunter_idx, next_phase):
        self.clear()
        self.title("🏹 HUNTER SHOOT")
        self.subtitle(
            f"Player {hunter_idx + 1} ({self.players[hunter_idx]}) eliminated! Choose a player to shoot."
        )

        self.player_buttons(
            partial(self.execute_hunter_shoot, next_phase=next_phase)
        )
        self.button(
            self.root,
            self.txt("⏭️ Pass", "放弃开枪"),
            partial(self.pass_hunter_shoot, next_phase=next_phase),
            width=25,
        ).pack(pady=10)
        self.speak_game("Hunter eliminated. Choose a target to shoot.", "猎人出局，请选择是否开枪带走一名玩家。")

    def execute_hunter_shoot(self, target, next_phase):
        self.alive[target] = False
        messagebox.showinfo(
            "🏹 Hunter Shot",
            f"Player {target + 1} ({self.players[target]}) was shot and eliminated!",
        )
        if target == self.sheriff:
            self.pending_sheriff_deaths.append(target)

        winner = self.check_winner()
        if winner:
            self.game_over(winner)
            return
        self.process_death_cascade(next_phase)

    def pass_hunter_shoot(self, next_phase):
        self.process_death_cascade(next_phase)

    def sheriff_badge_transfer_ui(self, sheriff_idx, next_phase):
        self.clear()
        self.title("👮 BADGE TRANSFER")
        self.subtitle(
            f"Sheriff Player {sheriff_idx + 1} ({self.players[sheriff_idx]}) eliminated!"
        )

        self.player_buttons(
            partial(self.execute_sheriff_transfer, next_phase=next_phase)
        )
        self.button(
            self.root,
            self.txt("💥 Tear Badge", "撕毁警徽"),
            partial(self.execute_sheriff_tear, next_phase=next_phase),
            width=25,
        ).pack(pady=10)

    def execute_sheriff_transfer(self, target, next_phase):
        self.sheriff = target
        messagebox.showinfo("👮 Badge Passed", f"Sheriff badge passed to Player {target + 1}")
        self.process_death_cascade(next_phase)

    def execute_sheriff_tear(self, next_phase):
        self.sheriff = None
        messagebox.showinfo("💥 Badge Destroyed", "The sheriff badge is destroyed.")
        self.process_death_cascade(next_phase)

    # -------------------------
    # DAY PHASE & KNIGHT SKILL
    # -------------------------

    def day_start(self, night_dead):
        self.clear()
        self.title(self.txt("☀️ DAYTIME", "天亮了"))

        if night_dead:
            text = f"{self.txt('Eliminated last night:', '昨晚死亡玩家：')}\n" + "\n".join(
                f"👤 Player {i + 1} ({self.players[i]})" for i in night_dead
            )
            speak_msg_en = "Day has come. Players were eliminated last night."
            speak_msg_zh = "天亮了，昨晚有玩家出局。"
        else:
            text = self.txt("🌅 It was a peaceful night. No one died.", "🌅 昨晚是平安夜，无人死亡。")
            speak_msg_en = "Day has come. It was a peaceful night."
            speak_msg_zh = "天亮了，昨晚是平安夜。"

        tk.Label(
            self.root,
            text=text,
            font=("Arial", 16, "bold"),
            fg="#c0392b" if night_dead else "#27ae60",
            wraplength=850,
        ).pack(pady=15)

        if not self.sheriff_elected and self.night == 0:
            self.button(
                self.root,
                self.txt("👮 Start Sheriff Election", "开始警长竞选"),
                partial(self.sheriff_election_phase, night_dead=night_dead),
                width=28,
            ).pack(pady=15)
        else:
            self.button(
                self.root,
                self.txt("➡️ Continue to Discussion", "进入发言讨论"),
                partial(self.day_discussion, night_dead=night_dead),
                width=28,
            ).pack(pady=15)

        self.speak_game(speak_msg_en, speak_msg_zh)

    def sheriff_election_phase(self, night_dead):
        self.clear()
        self.title("👮 SHERIFF ELECTION")
        self.subtitle(self.txt("Candidates speak, then vote for Sheriff.", "请竞选玩家发言，结束后选出警长。"))

        self.button(
            self.root,
            self.txt("🗳️ Confirm Elected Sheriff", "选出警长"),
            partial(self.select_sheriff_winner, night_dead=night_dead),
            width=28,
        ).pack(pady=10)
        self.button(
            self.root,
            self.txt("⚪ Skip Election", "无人当选"),
            partial(self.skip_sheriff_election, night_dead=night_dead),
            width=28,
        ).pack(pady=5)

    def select_sheriff_winner(self, night_dead):
        self.clear()
        self.title("👮 Select Elected Sheriff")
        self.player_buttons(
            partial(self.confirm_sheriff_winner, night_dead=night_dead)
        )

    def confirm_sheriff_winner(self, winner_idx, night_dead):
        self.sheriff = winner_idx
        self.sheriff_elected = True
        messagebox.showinfo(
            "👮 Sheriff Elected", f"🎉 Player {winner_idx + 1} elected Sheriff! (1.5x Vote Power)"
        )
        self.day_discussion(night_dead)

    def skip_sheriff_election(self, night_dead):
        self.sheriff = None
        self.sheriff_elected = True
        self.day_discussion(night_dead)

    def day_discussion(self, night_dead):
        self.clear()
        self.title(self.txt("🗣️ Daytime Discussion", "白天讨论阶段"))

        knight_idx = next(
            (
                i
                for i in range(self.player_count)
                if self.alive[i] and self.roles[i] == "Knight"
            ),
            None,
        )

        if knight_idx is not None and not self.knight_ability_used:
            self.button(
                self.root,
                self.txt("⚔️ [Knight Duel] Skill!", "⚔️ 骑士决斗技能！"),
                partial(self.knight_duel_start, knight_idx=knight_idx),
                width=30,
                bg="#e67e22",
            ).pack(pady=10)

        self.button(
            self.root, self.txt("🗳️ Start Voting", "发起投票"), self.voting, width=30, height=2
        ).pack(pady=20)
        self.speak_game("Please start daytime discussion.", "请大家开始发言讨论。")

    def knight_duel_start(self, knight_idx):
        self.clear()
        self.title("⚔️ Knight Duel")
        self.subtitle(
            f"Knight Player {knight_idx + 1} ({self.players[knight_idx]}) activated duel skill!"
        )
        self.subtitle(self.txt("Select a target to duel:", "选择要决斗的目标："))

        self.player_buttons(
            partial(self.execute_knight_duel, knight_idx=knight_idx),
            exclude_ids=[knight_idx],
        )

    def execute_knight_duel(self, target, knight_idx):
        self.knight_ability_used = True
        target_role = self.roles[target]

        if target_role == "Werewolf":
            self.alive[target] = False
            messagebox.showinfo(
                "⚔️ Duel Result",
                f"🎯 Success! Player {target + 1} is a 🐺 Werewolf!\nThey are eliminated immediately. Entering night phase!",
            )
            winner = self.check_winner()
            if winner:
                self.game_over(winner)
                return
            self.night += 1
            self.start_night()
        else:
            self.alive[knight_idx] = False
            messagebox.showinfo(
                "⚔️ Duel Result",
                f"❌ Failed! Player {target + 1} is a good guy!\nKnight is eliminated. Discussion continues.",
            )
            winner = self.check_winner()
            if winner:
                self.game_over(winner)
                return
            self.day_discussion(night_dead=[])

    # -------------------------
    # VOTING & IDIOT SKILL
    # -------------------------

    def voting(self):
        self.clear()
        self.title("🗳️ VOTING")
        self.subtitle(self.txt("Choose the player to eliminate.", "选择要淘汰的玩家。"))

        self.player_buttons(self.eliminate)
        self.button(
            self.root, self.txt("⚪ Tie / Skip Vote", "弃票/无人出局"), self.skip_vote, width=28
        ).pack(pady=10)

    def skip_vote(self):
        messagebox.showinfo("🗳️ Vote Result", "Tie or skip. No one was eliminated.")
        self.night += 1
        self.start_night()

    def eliminate(self, target):
        if self.roles[target] == "Idiot" and not self.idiot_revealed[target]:
            self.idiot_revealed[target] = True
            messagebox.showinfo(
                "🤡 Idiot Revealed",
                f"Player {target + 1} ({self.players[target]}) revealed Idiot card!\nSpared from elimination, stays in game without voting rights.",
            )
            self.night += 1
            self.start_night()
            return

        self.alive[target] = False
        messagebox.showinfo(
            "🗳️ Vote Result",
            f"Player {target + 1} ({self.players[target]}) was voted out and eliminated!",
        )

        if self.roles[target] == "Hunter":
            self.pending_hunter_deaths.append(target)
        if target == self.sheriff:
            self.pending_sheriff_deaths.append(target)

        winner = self.check_winner()
        if winner:
            self.game_over(winner)
            return

        self.process_death_cascade(
            next_phase=lambda: self.last_words_phase(target)
        )

    def last_words_phase(self, player_idx):
        self.clear()
        self.title("💬 LAST WORDS")
        self.subtitle(f"Player {player_idx + 1}, please give your last words.")

        def finish():
            stop_current_speech()
            self.night += 1
            self.start_night()

        self.button(
            self.root, self.txt("🌙 Enter Night Phase", "进入黑夜"), finish, width=28, height=2
        ).pack(pady=30)
        self.speak_game(f"Player {player_idx + 1}, please give your last words.", f"请 Player {player_idx + 1} 发表遗言。")

    # -------------------------
    # WIN CONDITION
    # -------------------------

    def check_winner(self):
        wolves = sum(
            1
            for i in range(self.player_count)
            if self.alive[i] and self.roles[i] == "Werewolf"
        )
        gods = sum(
            1
            for i in range(self.player_count)
            if self.alive[i] and ALL_ROLES[self.roles[i]]["side"] == "god"
        )
        villagers = sum(
            1
            for i in range(self.player_count)
            if self.alive[i] and ALL_ROLES[self.roles[i]]["side"] == "villager"
        )

        if wolves == 0:
            return self.txt("🏆 VILLAGERS WIN!", "🏆 好人阵营胜利！")
        if gods == 0 or villagers == 0:
            return self.txt("🐺 WEREWOLVES WIN!", "🐺 狼人阵营胜利！")
        return None

    def game_over(self, winner):
        self.clear()
        self.title("🏆 GAME OVER")
        tk.Label(
            self.root, text=winner, font=("Arial", 22, "bold"), fg="#27ae60"
        ).pack(pady=20)

        frame = tk.Frame(self.root)
        frame.pack(pady=10)

        for i in range(self.player_count):
            status = "❤️" if self.alive[i] else "💀"
            badge = "👮 " if i == self.sheriff else ""
            idiot_tag = " [🤡Idiot Revealed]" if self.idiot_revealed[i] else ""
            role_disp = self.get_role_display(self.roles[i])
            tk.Label(
                frame,
                text=f"{status} {badge}Player {i + 1}: {self.players[i]} - {role_disp}{idiot_tag}",
                font=("Arial", 11),
            ).pack(anchor="w", pady=2)

        self.button(
            self.root, self.txt("🔄 Restart Setup", "重新设置"), self.build_setup_config, width=25
        ).pack(pady=20)
        self.speak_game("Game Over.", "游戏结束。")


if __name__ == "__main__":
    root = tk.Tk()
    app = WerewolfJudge(root)
    root.mainloop()
