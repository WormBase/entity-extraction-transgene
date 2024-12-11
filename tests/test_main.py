import unittest
from unittest.mock import patch, MagicMock, ANY
import main


class TestTransgeneExtraction(unittest.TestCase):

    def setUp(self):
        # Set up any necessary test data or mocks
        self.mock_db_manager = MagicMock()
        self.mock_corpus_manager = MagicMock()
        self.mock_paper = MagicMock()

    def setup_cursor_mock(self):
        mock_cursor = MagicMock()
        self.mock_db_manager.generic.get_cursor.return_value.__enter__.return_value = mock_cursor
        # Simulate fetchone returning a valid integer id
        mock_cursor.fetchone.side_effect = [(1, ), (2, ), (1, ), (2, ), (3, )]  # or specific values as needed return mock_cursor

    @patch('main.WBDBManager')
    @patch('main.CorpusManager')
    def test_known_transgene_extraction(self, mock_cm, mock_db):
        # Arrange
        mock_db.return_value = self.mock_db_manager
        mock_cm.return_value = self.mock_corpus_manager
        self.mock_db_manager.generic.get_curated_transgenes.return_value = ['knownGene1', 'knownGene2']
        self.mock_paper.paper_id = 'WBPaper00000001'
        self.mock_paper.get_text_docs.return_value = [
            'This sentence contains knownGene1.',
            'Another sentence with knownGene2.'
        ]
        self.mock_corpus_manager.get_all_papers.return_value = [self.mock_paper]

        # Act
        main.main()

        # Assert
        expected_call = ('INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)', (ANY, '"WBPaper00000001"'))
        self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(*expected_call)

    @patch('main.WBDBManager')
    @patch('main.CorpusManager')
    def test_unknown_transgene_extraction(self, mock_cm, mock_db):
        # Arrange
        mock_db.return_value = self.mock_db_manager
        mock_cm.return_value = self.mock_corpus_manager
        self.mock_db_manager.generic.get_curated_transgenes.return_value = ['knownGene1']
        self.mock_paper.paper_id = 'WBPaper00000002'
        self.mock_paper.get_text_docs.return_value = [
            'This sentence contains an unknown transgene abcIs123.',
            'Another sentence with knownGene1.'
        ]
        self.mock_corpus_manager.get_all_papers.return_value = [self.mock_paper]

        self.setup_cursor_mock()

        # Act
        main.main()

        # Assert
        expected_call = ('INSERT INTO trp_name (id, object) VALUES (%s, %s)', (ANY, ANY))
        self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(*expected_call)
        expected_call = ('INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)', (ANY, 'abcIs123'))
        self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(*expected_call)

    @patch('main.WBDBManager')
    @patch('main.CorpusManager')
    def test_no_transgenes_found(self, mock_cm, mock_db):
        # Arrange
        mock_db.return_value = self.mock_db_manager
        mock_cm.return_value = self.mock_corpus_manager
        self.mock_db_manager.generic.get_curated_transgenes.return_value = ['knownGene1']
        self.mock_paper.paper_id = 'WBPaper00000003'
        self.mock_paper.get_text_docs.return_value = [
            'This sentence contains no transgenes.',
            'Another sentence without transgenes.'
        ]
        self.mock_corpus_manager.get_all_papers.return_value = [self.mock_paper]

        # Act
        main.main()

        # Assert
        self.mock_db_manager.generic.get_cursor().execute.assert_not_called()

    @patch('main.WBDBManager')
    @patch('main.CorpusManager')
    def test_multiple_papers(self, mock_cm, mock_db):
        # Arrange
        mock_db.return_value = self.mock_db_manager
        mock_cm.return_value = self.mock_corpus_manager
        self.mock_db_manager.generic.get_curated_transgenes.return_value = ['knownGene1']
        paper1 = MagicMock()
        paper1.paper_id = 'WBPaper00000004'
        paper1.get_text_docs.return_value = ['This paper mentions knownGene1.']
        paper2 = MagicMock()
        paper2.paper_id = 'WBPaper00000005'
        paper2.get_text_docs.return_value = ['This paper has an unknown transgene xyzIs456.']
        self.mock_corpus_manager.get_all_papers.return_value = [paper1, paper2]

        self.setup_cursor_mock()

        # Act
        main.main()

        # Assert
        self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(
            "INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
            (unittest.mock.ANY, '"WBPaper00000004"')
        )
        self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(
            "INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
            (unittest.mock.ANY, 'xyzIs456')
        )

    @patch('main.WBDBManager')
    @patch('main.CorpusManager')
    def test_multiple_unknown_transgenes(self, mock_cm, mock_db):
        # Arrange
        mock_db.return_value = self.mock_db_manager
        mock_cm.return_value = self.mock_corpus_manager
        self.mock_db_manager.generic.get_curated_transgenes.return_value = ['knownGene1']
        paper = MagicMock()
        paper.paper_id = 'WBPaper00000006'
        paper.get_text_docs.return_value = [
            'This paper mentions an unknown transgene abcIs789.',
            'It also talks about xyzEx101 and defIs202.',
            'There\'s also a known gene knownGene1 and another unknown pqrIs303.'
        ]
        self.mock_corpus_manager.get_all_papers.return_value = [paper]

        self.setup_cursor_mock()

        # Act
        main.main()

        # Assert
        # Check if the paper is inserted
        self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(
            "INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
            (unittest.mock.ANY, '"WBPaper00000006"')
        )

        # Check if all unknown transgenes are inserted
        expected_transgenes = ['abcIs789', 'xyzEx101', 'defIs202', 'pqrIs303']
        for transgene in expected_transgenes:
            self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(
                "INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
                (unittest.mock.ANY, transgene)
            )

        # Check that knownGene1 is not inserted as an unknown transgene
        with self.assertRaises(AssertionError):
            self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(
                "INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
                (unittest.mock.ANY, 'knownGene1')
            )

    @patch('main.WBDBManager')
    @patch('main.CorpusManager')
    def test_edge_cases_unknown_transgenes(self, mock_cm, mock_db):
        # Arrange
        mock_db.return_value = self.mock_db_manager
        mock_cm.return_value = self.mock_corpus_manager
        self.mock_db_manager.generic.get_curated_transgenes.return_value = ['knownGene1']
        paper = MagicMock()
        paper.paper_id = 'WBPaper00000007'
        paper.get_text_docs.return_value = [
            'This paper mentions a transgene with unusual naming abcIs789def.',
            'It also talks about a potential false positive XYZIs101.',
            'There\'s a transgene at the end of a sentence: pqrIs303.',
            'A transgene (defIs202) within parentheses.',
            'Two transgenes in one sentence: ghjIs505 and jklEx606.'
        ]
        self.mock_corpus_manager.get_all_papers.return_value = [paper]

        self.setup_cursor_mock()

        # Act
        main.main()

        # Assert
        # Check if the paper is inserted
        self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(
            "INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
            (unittest.mock.ANY, '"WBPaper00000007"')
        )

        # Check if all valid unknown transgenes are inserted
        expected_transgenes = ['XYZIs101', 'pqrIs303', 'defIs202', 'ghjIs505', 'jklEx606']
        for transgene in expected_transgenes:
            self.mock_db_manager.generic.get_cursor().__enter__().execute.assert_any_call(
                "INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
                (unittest.mock.ANY, transgene)
            )


if __name__ == '__main__':
    unittest.main()
