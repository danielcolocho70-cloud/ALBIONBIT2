import unittest

from cogs.redsec_chat import ReyChat


class ReyChatTests(unittest.TestCase):

    def test_sanitize_answer_removes_generic_ai_identity(self):
        chat = ReyChat.__new__(ReyChat)
        answer = "Soy ChatGPT, basado en la arquitectura GPT-4 de OpenAI."

        cleaned = chat._sanitize_answer(answer)

        self.assertNotIn("ChatGPT", cleaned)
        self.assertNotIn("OpenAI", cleaned)
        self.assertIn("Rey", cleaned)

    def test_system_prompt_mentions_albion_and_real_item_names(self):
        prompt = ReyChat._build_system_prompt()

        self.assertIn("Albion Online", prompt)
        self.assertIn("Holy Staff", prompt)
        self.assertIn("Cleric Robe", prompt)

    def test_system_prompt_allows_general_and_casual_conversation(self):
        prompt = ReyChat._build_system_prompt()

        self.assertIn("saludos, bromas", prompt)
        self.assertIn("preguntas absurdas", prompt)
        self.assertIn("planes del clan", prompt)
        self.assertIn("No inventes ítems", prompt)

    def test_voice_commands_are_detected(self):
        chat = ReyChat.__new__(ReyChat)

        self.assertEqual(chat._is_voice_command("entra rey a voz"), "join")
        self.assertEqual(chat._is_voice_command("rey desconectate"), "leave")
        self.assertEqual(chat._is_voice_command("rey escucha"), "listen_join")
        self.assertEqual(chat._is_voice_command("rey deja de escuchar"), "listen_leave")
        self.assertIsNone(chat._is_voice_command("vamos a hacer roaming"))

    def test_voice_wake_word_accepts_common_transcription_variants(self):
        from cogs.redsec_chat import VOICE_WAKE_PATTERN

        self.assertIsNotNone(VOICE_WAKE_PATTERN.search("Rey, me escuchas"))
        self.assertIsNotNone(VOICE_WAKE_PATTERN.search("Hey, me escuchas"))
        self.assertIsNotNone(VOICE_WAKE_PATTERN.search("Rei, responde"))

    def test_get_build_response_for_healer_t4_2(self):
        chat = ReyChat.__new__(ReyChat)
        result = chat._get_build_response("dime una build para healer t4.2")

        self.assertIsNotNone(result)
        self.assertIn("Holy Staff T4.2", result)
        self.assertIn("Cleric Robe T4.2", result)

    def test_get_build_response_for_healer_t4_1(self):
        chat = ReyChat.__new__(ReyChat)
        result = chat._get_build_response("dime una build para healer t4.1")

        self.assertIsNotNone(result)
        self.assertIn("Holy Staff T4.1", result)
        self.assertIn("Cleric Robe T4.1", result)

    def test_get_build_response_for_tank_t4_2(self):
        chat = ReyChat.__new__(ReyChat)
        result = chat._get_build_response("¿me das una build de tank t4.2?")

        self.assertIsNotNone(result)
        self.assertIn("Incubus Mace", result)
        self.assertIn("Guardian Armor", result)

    def test_get_build_response_for_dps_t4_2(self):
        chat = ReyChat.__new__(ReyChat)
        result = chat._get_build_response("build t4.2 dps")

        self.assertIsNotNone(result)
        self.assertIn("Bear Paws", result)
        self.assertIn("Hunter Jacket", result)
