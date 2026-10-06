import unittest

from lib.rpdb import imdb_id, poster_url


class RpdbPosterTests(unittest.TestCase):
    def test_uses_imdb_id_with_enabled_remote_key(self):
        row = {'id': 'tt1234567', 'poster': 'https://example.test/original.jpg'}
        url = poster_url(row, settings={'rpdbEnabled': True, 'rpdbApiKey': 'abc-123'})
        self.assertEqual(
            url,
            'https://api.ratingposterdb.com/abc-123/imdb/poster-default/tt1234567.jpg'
        )

    def test_extracts_series_imdb_from_episode_style_identity(self):
        self.assertEqual(imdb_id({'id': 'tt7654321:2:4'}), 'tt7654321')

    def test_falls_back_when_disabled_or_no_imdb_id(self):
        fallback = 'https://example.test/original.jpg'
        self.assertEqual(
            poster_url({'id': 'tmdb:123', 'poster': fallback},
                       settings={'rpdbEnabled': True, 'rpdbApiKey': 'abc-123'}),
            fallback
        )
        self.assertEqual(
            poster_url({'id': 'tt1234567', 'poster': fallback},
                       settings={'rpdbEnabled': False, 'rpdbApiKey': 'abc-123'}),
            fallback
        )


if __name__ == '__main__':
    unittest.main()
