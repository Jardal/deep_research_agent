import json
import os
import time
import requests

# Konfigurace lokálního serveru (např. llama-server z Prism-ML)
LLAMA_SERVER_URL = "http://localhost:8080/v1/chat/completions"
KV_RESET_URL = "http://localhost:8080/slots"  # Endpoint pro správu slotů/KV cache v llama.cpp


class ResearchMemory:
  """Třívrstvá RAG paměť pro uchovávání stavu výzkumu v rámci aktuální session."""

  def __init__(self):
    self.confirmed_facts = []  # Ověřené a získané informace
    self.open_questions = []  # Pojmy a otázky, které je nutné prozkoumat
    self.dead_ends = []  # Slepé cesty / orbity (vyřešené neúspěchem)

  def add_fact(self, fact):
    if fact not in self.confirmed_facts:
      self.confirmed_facts.append(fact)

  def add_question(self, q):
    if q not in self.open_questions and q not in self.dead_ends:
      self.open_questions.append(q)

  def add_dead_end(self, dead_end):
    if dead_end not in self.dead_ends:
      self.dead_ends.append(dead_end)
    # Pokud byla otázka v otevřených, odstraníme ji
    if dead_end in self.open_questions:
      self.open_questions.remove(dead_end)

  def get_context_string(self):
    return f"""
=== OVĚŘENÉ FAKTY ({len(self.confirmed_facts)}) ===
{chr(10).join([f"- {f}" for f in self.confirmed_facts]) if self.confirmed_facts else "Zatím žádné."}

=== OTEVŘENÉ OTÁZKY K PROZKOUMÁNÍ ({len(self.open_questions)}) ===
{chr(10).join([f"- {q}" for q in self.open_questions]) if self.open_questions else "Žádné zbývající otázky."}

=== SLEPÉ CESTY / ORBITKY (NEVSTUPOVAT) ({len(self.dead_ends)}) ===
{chr(10).join([f"- {d}" for d in self.dead_ends]) if self.dead_ends else "Žádné slepé cesty."}
"""


def call_llm(system_prompt, user_content):
  """Komunikace s lokálním llama-serverem (OpenAI compatible API)."""
  headers = {"Content-Type": "application/json"}
  payload = {
      "model": "local-model",
      "messages": [
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_content},
      ],
      "temperature": 0.2,  # Nízká teplota pro faktickou přesnost a stabilitu formátu
      "max_tokens": 800,
  }

  try:
    response = requests.post(
        LLAMA_SERVER_URL, headers=headers, json=payload, timeout=120
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
  except Exception as e:
    print(f"❌ Chyba při komunikaci s llama-serverem: {e}")
    return "CHYBA_SERVERU"


def reset_kv_cache():
  """Tvrdý reset KV cache na llama-serveru přes slot management."""
  print(
      "🧹 [KV CACHE RESET] Provádím vymazání cache a uvolnění kontextu na"
      " serveru..."
  )
  try:
    # V llama.cpp lze vynulovat slot (defaultně slot id 0)
    requests.post(
        f"{KV_RESET_URL}?action=save", json={}
    )  # případně specifický endpoint dle verze llama.cpp
    # Bezpečnější univerzální trik pro vyčištění slotu v llama-server:
    requests.post(
        "http://localhost:8080/slots/0?action=erase", timeout=5
    )
    time.sleep(1)
  except Exception:
    # Pokud endpoint slotů není podporován, server to ignoruje, hlavní je že session běží dál
    pass


def mock_wikiskript_search(term):
  """Simulace vyhledávání v ZIM archivu / Wikiskriptech.

  (Zde nahradíte reálným dotazem do lokální knihovny libzim / SQLite).
  """
  print(f"🔍 [ZIM SEARCH] Prohledávám Wikiskripta pro termín: '{term}'...")
  time.sleep(0.5)  # simulace I/O operace
  # Zde by proběhla reálná extrakce textu ze ZIM souboru
  return f"Odborný text z Wikiskript pro pojem '{term}': Obsahuje klíčové mechanismy, patofyziologii a klinické doporučení."


def run_autonomous_research(initial_topic, max_iterations=30):
  memory = ResearchMemory()
  memory.add_question(initial_topic)

  system_prompt = (
      "Jsi autonomní výzkumný agent. Tvým úkolem je hloubkově prozkoumat zadané"
      " téma pomocí iterativního získávání faktů. Sleduješ strukturovanou paměť."
      " V každém kroku musíš odpovědět POUZE v jednom z následujících formátů:\n\n"
      "1. Pokud potřebuješ prozkoumat nový pojem z otevřených otázek, napiš:"
      " VYHLEDAT: [přesný pojem]\n"
      "2. Pokud máš nové zjištění, zapiš ho: FAKT: [popis zjištění]\n"
      "3. Pokud zjistíš, že ses zacyklil, kroužíš kolem toho samého nebo narazíš"
      " na neřešitelnou slepou uličku, napiš výhradně klíčové slovo: ORBITA\n"
      "4. Pokud jsou všechny otevřené otázky zodpovězeny a výzkum je hotov,"
      " napiš: VÝZKUM HOTOV"
  )

  print(
      f"🚀 Spouštím hloubkový výzkum (27B model) pro téma: '{initial_topic}'\n"
  )

  for iteration in range(1, max_iterations + 1):
    print(f"\n================ ITERACE {iteration} ================")

    # Pokud nemáme co zkoumat, končíme
    if not memory.open_questions:
      print("✅ Žádné další otevřené otázky. Výzkum dospěl ke konci.")
      break

    # Sestavení aktuálního kontextu pro model
    current_focus = memory.open_questions[0]
    user_payload = f"""
AKTUÁLNÍ CÍL / OTÁZKA K ŘEŠENÍ: {current_focus}

DOSAVADNÍ STAV VÝZKUMU (RAG PAMĚŤ):
{memory.get_context_string()}

Rozhodni o dalším kroku (VYHLEDAT / FAKT / ORBITA / VÝZKUM HOTOV):
"""

    response = call_llm(system_prompt, user_payload).strip()
    print(f"🤖 Odezva modelu:\n{response}\n")

    # --- 1. DETEKCE ORBITY (Zacyklení) ---
    if "ORBITA" in response:
      print(
          "⚠️ [ORBITA DETEKOVÁNA] Agent signalizuje zacyklení nebo slepou"
          " uličku!"
      )
      memory.add_dead_end(current_focus)
      reset_kv_cache()
      continue

    # --- 2. DOKONČENÍ VÝZKUMU ---
    if "VÝZKUM HOTOV" in response:
      print("🎉 Agent vyhodnotil výzkum jako kompletní.")
      break

    # --- 3. ZPRACOVÁNÍ NÁSTROJE (VYHLEDAT) ---
    if "VYHLEDAT:" in response:
      try:
        term = response.split("VYHLEDAT:")[1].split("\n")[0].strip()
        search_result = mock_wikiskript_search(term)

        # Přidáme výsledek do faktů a odmažeme z otevřených otázek
        memory.add_fact(f"Zjištění z '{term}': {search_result}")

        # Zde může model v reálném provozu generovat další podotázky z textu
        # Pro zjednodušení harnessu přidáme do otevřených otázek související kontext
        sub_term = f"Detailní mechanizmus: {term}"
        memory.add_question(sub_term)

      except Exception as e:
        print(f"❌ Chyba při parsování příkazu VYHLEDAT: {e}")

    # --- 4. ZÁPIS NOVÉHO FAKTU ---
    elif "FAKT:" in response:
      try:
        fact_text = response.split("FAKT:")[1].split("\n")[0].strip()
        memory.add_fact(fact_text)
        # Úspěšně jsme vyřešili aktuální fokus, přesuneme ho z otevřených otázek
        if current_focus in memory.open_questions:
          memory.open_questions.remove(current_focus)
      except Exception as e:
        print(f"❌ Chyba při parsování FAKTU: {e}")

    # Krátká pauza mezi iteracemi pro klid procesoru a chlazení v Termuxu
    time.sleep(1)

  # --- FINÁLNÍ EXPORT ZNALOSTÍ ---
  print("\n================ VÝZKUM DOKONČEN ================")
  output_filename = f"vyzkum_{int(time.time())}.json"

  final_data = {
      "topic": initial_topic,
      "confirmed_facts": memory.confirmed_facts,
      "dead_ends": memory.dead_ends,
  }

  with open(output_filename, "w", encoding="utf-8") as f:
    json.dump(final_data, f, ensure_ascii=False, indent=2)

  print(
      f"💾 Ověřené globální znalosti byly uloženy do souboru: {output_filename}"
  )
  print(
      "Tyto znalosti nyní můžete pomocí lokálního embedding modelu začlenit do"
      " trvalé globální RAG databáze."
  )


if __name__ == "__main__":
  # Příklad spuštění pro noční běh v Termuxu
  run_autonomous_research(
      initial_topic="Komplikace a patofyziologie anafylaktického šoku"
  )