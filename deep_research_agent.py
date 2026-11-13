import json
import os
import time
import requests

# Konfigurace lokálního serveru (např. llama-server s 27B ternárním modelem)
LLAMA_SERVER_URL = "http://localhost:8080/v1/chat/completions"
KV_RESET_URL = "http://localhost:8080/slots/0?action=erase"


class ResearchMemory:
  """Třívrstvá RAG paměť pro uchovávání stavu výzkumu v hlavní větvi."""

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


def call_llm(system_prompt, user_content, max_tokens=800):
  """Univerzální funkce pro komunikaci s lokálním llama-serverem."""
  headers = {"Content-Type": "application/json"}
  payload = {
      "model": "local-model",
      "messages": [
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_content},
      ],
      "temperature": 0.2,
      "max_tokens": max_tokens,
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


def sub_agent_extract_knowledge(raw_text_chunk, research_question):
  """STROMOVÉ VĚTVENÍ (SUB-AGENT):

  Zpracuje obří surový text v čistě statickém, izolovaném kontextu.
  Do hlavní KV cache hlavní větve se uloží jen čistý výsledek.
  """
  print(
      "🌲 [SUB-AGENT VĚTVEVNÍ] Spouštím izolovanou analýzu surového textu"
      " stranou od hlavního kontextu..."
  )

  system_prompt = (
      "Jsi specializovaný rešeršní extraktor. Tvým jediným úkolem je přečíst"
      " dodaný surový text a vyextrahovat z něj přesné, faktické body vztahující"
      " se k zadané otázce. Ignoruj navigační prvky a šum. Piš stručně a věcně."
  )
  user_payload = f"VÝZKUMNÁ OTÁZKA: {research_question}\n\nSUROVÝ TEXT Z WIKISKRIPT:\n{raw_text_chunk[:8000]}"

  # Voláme model jako bezstavovou funkci (neovlivňuje hlavní historii)
  extracted_summary = call_llm(system_prompt, user_payload, max_tokens=400)
  print("🌿 [SUB-AGENT] Analýza dokončena, dočasný kontext zahozen.")
  return extracted_summary


def reset_kv_cache():
  """Tvrdý reset KV cache na llama-serveru při detekci orbity."""
  print(
      "🧹 [KV CACHE RESET] Mazání slotu na serveru z důvodu detekce orbity..."
  )
  try:
    requests.post(KV_RESET_URL, timeout=5)
    time.sleep(1)
  except Exception:
    pass


def fetch_zim_article_mock(term):
  """Simulace čtení surového HTML/textu ze souboru .zim (Wikiskripta)."""
  print(
      f"🔍 [ZIM ARCHIVE] Stahuji plný text článku pro pojem: '{term}'"
      " (potenciálně velký text)..."
  )
  time.sleep(0.5)
  # Zde by v praxi proběhlo parsování přes libzim a BeautifulSoup
  return (
      f"[Surový text Wikiskript pro {term}]: Obsahuje detailní patofyziologii,"
      " diagnostická kritéria, diferenciální diagnózu a terapeutické postupy,"
      " včetně rizikových faktorů a kazuistik."
  )


def run_autonomous_research(initial_topic, max_iterations=30):
  memory = ResearchMemory()
  memory.add_question(initial_topic)

  system_prompt = (
      "Jsi hlavní výzkumný agent. Řídíš hloubkový výzkum. Sleduješ strukturovanou"
      " paměť. V každém kroku musíš odpovědět POUZE v jednom z formátů:\n\n"
      "1. VYHLEDAT: [přesný pojem k prozkoumání]\n"
      "2. FAKT: [stručný popis ověřeného zjištění]\n"
      "3. ORBITA (pokud se točíš v kruhu nebo narážíš na slepou uličku)\n"
      "4. VÝZKUM HOTOV"
  )

  print(
      f"🚀 Spouštím hloubkový výzkum (27B model + Sub-Agent Tree) pro téma:"
      f" '{initial_topic}'\n"
  )

  for iteration in range(1, max_iterations + 1):
    print(f"\n================ ITERACE {iteration} ================")

    if not memory.open_questions:
      print("✅ Žádné další otevřené otázky. Výzkum dospěl ke konci.")
      break

    current_focus = memory.open_questions[0]
    user_payload = f"""
AKTUÁLNÍ CÍL / OTÁZKA K ŘEŠENÍ: {current_focus}

DOSAVADNÍ STAV VÝZKUMU (RAG PAMĚŤ):
{memory.get_context_string()}

Rozhodni o dalším kroku (VYHLEDAT / FAKT / ORBITA / VÝZKUM HOTOV):
"""

    response = call_llm(system_prompt, user_payload).strip()
    print(f"🤖 Odezva hlavního agenta:\n{response}\n")

    # --- 1. DETEKCE ORBITY ---
    if "ORBITA" in response:
      print(
          "⚠️ [ORBITA DETEKOVÁNA] Hlavní agent signalizuje zacyklení nebo slepou"
          " uličku!"
      )
      memory.add_dead_end(current_focus)
      reset_kv_cache()
      continue

    # --- 2. DOKONČENÍ VÝZKUMU ---
    if "VÝZKUM HOTOV" in response:
      print("🎉 Hlavní agent vyhodnotil výzkum jako kompletní.")
      break

    # --- 3. VYHLEDÁVÁNÍ A STROMOVÉ VĚTVENÍ (SUB-AGENT) ---
    if "VYHLEDAT:" in response:
      try:
        term = response.split("VYHLEDAT:")[1].split("\n")[0].strip()

        # A) Získání surových dat z externího zdroje (.zim / Wikiskripta)
        raw_article_text = fetch_zim_article_mock(term)

        # B) Izolované zpracování přes Sub-Agenta (stromové odbočení)
        # Hlavní kontext 27B modelu se nezahltí tisíci slovy surového textu.
        distilled_knowledge = sub_agent_extract_knowledge(
            raw_article_text, current_focus
        )

        # C) Do hlavní paměti se uloží pouze čistý extrakt
        memory.add_fact(
            f"Zjištění z rešerše '{term}':\n{distilled_knowledge}"
        )

        # Vygenerujeme další navazující podotázku do fronty
        memory.add_question(f"Detailní aspekty pojmu: {term}")

      except Exception as e:
        print(f"❌ Chyba při zpracování nástroje VYHLEDAT: {e}")

    # --- 4. ZÁPIS NOVÉHO FAKTU ---
    elif "FAKT:" in response:
      try:
        fact_text = response.split("FAKT:")[1].split("\n")[0].strip()
        memory.add_fact(fact_text)
        if current_focus in memory.open_questions:
          memory.open_questions.remove(current_focus)
      except Exception as e:
        print(f"❌ Chyba při parsování FAKTU: {e}")

    time.sleep(1)

  # --- FINÁLNÍ EXPORT ---
  print("\n================ VÝZKUM DOKONČEN ================")
  output_filename = f"vyzkum_tree_{int(time.time())}.json"
  final_data = {
      "topic": initial_topic,
      "confirmed_facts": memory.confirmed_facts,
      "dead_ends": memory.dead_ends,
  }

  with open(output_filename, "w", encoding="utf-8") as f:
    json.dump(final_data, f, ensure_ascii=False, indent=2)

  print(f"💾 Výsledky uloženy do souboru: {output_filename}")


if __name__ == "__main__":
  run_autonomous_research(
      initial_topic="Komplikace a patofyziologie anafylaktického šoku"
  )
