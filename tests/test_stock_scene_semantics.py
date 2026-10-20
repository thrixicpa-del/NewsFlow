"""Civilian maritime narration must retain scene objects, not a topic portrait."""
import unittest

from scriptor.bridge import _semantic_clip_ok
from scriptor.footage import FootageItem
from scriptor.timeline import GENERIC_VISUAL_QUERY, fallback_visual_query


class MaritimeSceneQueryTests(unittest.TestCase):
    def test_civilian_harbor_actions_produce_concrete_queries(self):
        cases = [
            ('На причале разбирали плавучие секции.', ('pier', 'pontoon')),
            ('Буксиры разворачивались к понтонам.', ('tugboat', 'pontoon')),
            ('Сухогруз дал задний ход и отошел от швартовов.', ('cargo ship', 'mooring')),
            ('Суда вышли в море с грузом.', ('ship', 'maritime')),
            ('Таможенники сверяли грузовые манифесты.', ('customs', 'documents')),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                query = fallback_visual_query(text)
                self.assertNotEqual(query, GENERIC_VISUAL_QUERY)
                self.assertTrue(any(word in query for word in expected), query)
                self.assertNotIn('navy', query)
                self.assertNotIn('Aliyev', query)

    def test_ordinary_cargo_ship_and_warehouse_do_not_invent_navy_or_fire(self):
        query = fallback_visual_query('Корабль с грузом шел к складской площадке.')
        self.assertIn('ship', query)
        self.assertIn('warehouse', query)
        self.assertNotIn('navy', query)
        self.assertNotIn('fire', query)
        self.assertNotIn('emergency', query)

    def test_road_transport_is_not_a_seaport_and_court_is_not_a_ship(self):
        self.assertNotIn('seaport', fallback_visual_query('Автотранспорт доставил груз на склад.'))
        self.assertNotIn('ship', fallback_visual_query('Суды рассмотрели манифест общественного движения.'))

    def test_explicit_fire_and_naval_vessel_keep_their_actual_subject(self):
        self.assertIn('fire', fallback_visual_query('На складе пожар, работают пожарные.'))
        self.assertIn('navy', fallback_visual_query('Военный корабль и эсминец вышли на учения.'))

    def test_explicit_naval_action_does_not_acquire_civilian_cargo_context(self):
        for text in ('Эсминец вышел в море на военные учения.',
                     'На военном корабле экипаж вышел в море.', 'Военное судно вышло в море.'):
            with self.subTest(text=text):
                query = fallback_visual_query(text)
                self.assertIn('navy', query)
                self.assertNotIn('civilian', query)
                self.assertNotIn('cargo', query)

    def test_legal_manifest_and_passports_do_not_invent_shipping(self):
        for text in ('Суд рассмотрел политический манифест и паспорта участников.',
                     'Решение судов по манифесту.'):
            with self.subTest(text=text):
                self.assertNotIn('shipping', fallback_visual_query(text))


class MaritimePortraitGuardTests(unittest.TestCase):
    def test_port_scene_does_not_accept_a_politician_portrait(self):
        for name in ('Portrait of Ilham Aliyev', 'Nikol Pashinyan press conference', 'Vladimir Putin speech'):
            with self.subTest(name=name):
                item = FootageItem('', name, 'wikimedia')
                self.assertFalse(_semantic_clip_ok('civilian harbor pier cargo ships', item))

    def test_explicit_person_statement_can_still_use_that_person(self):
        self.assertTrue(_semantic_clip_ok('Ilham Aliyev press conference about port policy',
                        FootageItem('', 'Portrait of Ilham Aliyev', 'wikimedia')))

    def test_explicit_portrait_is_not_a_port_object_even_when_title_names_port(self):
        self.assertFalse(_semantic_clip_ok('harbor pier cargo ships',
                         FootageItem('', 'Portrait of Ilham Aliyev at Baku port', 'wikimedia')))

    def test_port_opening_object_photo_is_not_rejected_just_for_event_author(self):
        self.assertTrue(_semantic_clip_ok('harbor pier cargo ships', FootageItem('',
            'Ilham Aliyev inaugurated RO-RO terminal at Baku International Sea Trade Port complex 27', 'wikimedia')))

    def test_generic_filename_under_an_old_politician_folder_is_not_a_portrait_verdict(self):
        item = FootageItem('D:/old/putin/processed_oil_1/slice18.mp4', 'slice18.mp4')
        self.assertTrue(_semantic_clip_ok('civilian harbor pier cargo ships', item))
