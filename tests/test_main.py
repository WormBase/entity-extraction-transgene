import unittest
from unittest.mock import patch, MagicMock
import main


class TestTransgeneExtraction(unittest.TestCase):

    def setUp(self):
        # Set up any necessary test data or mocks
        self.mock_db_manager = MagicMock()
        self.mock_corpus_manager = MagicMock()
        self.mock_paper = MagicMock()

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
        self.mock_db_manager.generic.get_cursor().execute.assert_any_call(
            "INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
            (unittest.mock.ANY, '"WBPaper00000001"')
        )

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

        # Act
        main.main()

        # Assert
        self.mock_db_manager.generic.get_cursor().execute.assert_any_call(
            "INSERT INTO trp_name (id, object) VALUES (%s, %s)",
            (unittest.mock.ANY, unittest.mock.ANY)
        )
        self.mock_db_manager.generic.get_cursor().execute.assert_any_call(
            "INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
            (unittest.mock.ANY, 'abcIs123')
        )

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

        # Act
        main.main()

        # Assert
        self.mock_db_manager.generic.get_cursor().execute.assert_any_call(
            "INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
            (unittest.mock.ANY, '"WBPaper00000004"')
        )
        self.mock_db_manager.generic.get_cursor().execute.assert_any_call(
            "INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
            (unittest.mock.ANY, 'xyzIs456')
        )


if __name__ == '__main__':
    unittest.main()