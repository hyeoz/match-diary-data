import unittest

from scripts.fetch_kbo_schedule import html_texts, parse_date, parse_rows, status_for


class ScheduleToolsTest(unittest.TestCase):
    def test_html_and_date_parsing(self):
        self.assertEqual(html_texts('<b>18:30</b>'), ['18:30'])
        self.assertEqual(parse_date('09.01(화)', 2026), '2026-09-01')

    def test_status(self):
        self.assertEqual(status_for('', 3, 1), 'final')
        self.assertEqual(status_for('우천취소', None, None), 'canceled')
        self.assertEqual(status_for('', None, None), 'scheduled')

    def test_schedule_row_parsing(self):
        payload = {
            'rows': [
                {
                    'row': [
                        {'Class': 'day', 'Text': '09.01(화)'},
                        {'Class': 'time', 'Text': '<b>18:30</b>'},
                        {'Class': 'play', 'Text': '<span>LG</span><em><span>3</span><span>vs</span><span>1</span></em><span>두산</span>'},
                        {'Text': "<a href='/Game?gameId=20260901LGOB0'>리뷰</a>"},
                        {'Text': ''}, {'Text': ''}, {'Text': ''},
                        {'Text': '잠실'}, {'Text': '-'},
                    ]
                }
            ]
        }
        game = parse_rows(payload, 2026, 'regular')[0]
        self.assertEqual(game['id'], '20260901LGOB0')
        self.assertEqual(game['awayTeamId'], 2)
        self.assertEqual(game['homeTeamId'], 9)
        self.assertEqual(game['status'], 'final')
        self.assertEqual(game['stadiumId'], 'jamsil')


if __name__ == '__main__':
    unittest.main()

