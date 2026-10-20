"""Civilian maritime narration must retain scene objects, not a topic portrait."""
import unittest

from scriptor.bridge import (
    _montage_query_ladder,
    _montage_query_variants,
    _semantic_clip_ok,
)
from scriptor.footage import FootageItem
from scriptor.timeline import GENERIC_VISUAL_QUERY, fallback_visual_query


class AviationSceneQueryTests(unittest.TestCase):
    def test_airport_context_is_not_invented_from_port_substring(self):
        for query in ('empty airport terminal', 'aircraft flight airport runway'):
            with self.subTest(query=query):
                ladder = _montage_query_ladder(query)
                contexts = ' '.join(ladder['CATEGORY_MATCH'] + ladder['SAFE_CONTEXT'])
                self.assertIn('airport', contexts)
                self.assertNotIn('oil', contexts)
                self.assertNotIn('cargo port', contexts)
                self.assertNotIn('oil tanker', ' '.join(_montage_query_variants(query)))
        self.assertNotIn('oil tanker', ' '.join(_montage_query_ladder('agricultural soil harvest')['CATEGORY_MATCH']))

    def test_empty_terminal_does_not_accept_an_explicit_aircraft_action(self):
        for name in ('Plane Spotting FedEx Air Cargo Takeoff Runway',
                     'AirBridgeCargo Boeing 747 landing at airport',
                     "Crossing Gibraltar's Airport Runway.webm",
                     'Landing and taking off at the most dangerous airport in the world',
                     'Самолёт взлетает с полосы аэропорта'):
            with self.subTest(name=name):
                self.assertFalse(_semantic_clip_ok('empty airport terminal', FootageItem('', name, 'wikimedia')))

    def test_empty_terminal_keeps_terminal_context_and_generic_files(self):
        for name in ('Empty airport terminal during COVID-19',
                     'Passenger terminal airport check-in hall', 'slice18.mp4'):
            with self.subTest(name=name):
                self.assertTrue(_semantic_clip_ok('empty airport terminal', FootageItem(
                    'D:/old/aircraft/takeoff/' + name, name, 'wikimedia')))
        self.assertTrue(_semantic_clip_ok('aircraft flight airport runway', FootageItem(
            '', 'Plane Spotting FedEx Air Cargo Takeoff Runway', 'wikimedia')))

    def test_empty_airport_terminal_does_not_request_aircraft_in_flight(self):
        query = fallback_visual_query('Прибрежный аэропорт давно не принимал пассажиров, терминал опустел.')
        self.assertIn('empty airport terminal', query)
        self.assertNotIn('aircraft', query)
        self.assertNotIn('empty airport terminal', fallback_visual_query('Грузовой терминал опустел.'))
        self.assertNotIn('empty airport terminal', fallback_visual_query('Аэропорт работает, терминал не опустел.'))

    def test_airport_objects_are_concrete_without_a_maritime_substitution(self):
        cases = (
            ('Диспетчер аэропорта увидел самолет на взлетной полосе.', 'aircraft'),
            ('Пассажирский самолёт продолжал лететь над морем.', 'aircraft'),
            ('Воздушное судно направили на запасную полосу.', 'aircraft'),
            ('На радаре возникла движущаяся отметка.', 'radar'),
            ('В диспетчерской башне не горел свет.', 'control'),
        )
        for text, subject in cases:
            with self.subTest(text=text):
                query = fallback_visual_query(text)
                self.assertIn(subject, query)
                self.assertNotIn('cargo ship', query)
                self.assertNotIn('harbor', query)

    def test_dispatcher_and_terminal_are_not_automatically_airports(self):
        self.assertNotIn('aircraft', fallback_visual_query('Диспетчер железной дороги проверил грузовой терминал.'))

    def test_military_aircraft_are_not_ground_vehicles_or_civilian_passenger_planes(self):
        query = fallback_visual_query('Военный самолёт поднялся с аэродрома.')
        self.assertIn('military aircraft', query)
        self.assertNotIn('military vehicles', query)
        self.assertNotIn('passenger', query)


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
