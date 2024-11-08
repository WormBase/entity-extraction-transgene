import argparse
import logging
import re
from collections import defaultdict

from wbtools.db.dbmanager import WBDBManager
from wbtools.literature.corpus import CorpusManager


logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="String matching pipeline for antibody")
    parser.add_argument("-N", "--db-name", metavar="db_name", dest="db_name", type=str)
    parser.add_argument("-U", "--db-user", metavar="db_user", dest="db_user", type=str)
    parser.add_argument("-P", "--db-password", metavar="db_password", dest="db_password", type=str, default="")
    parser.add_argument("-H", "--db-host", metavar="db_host", dest="db_host", type=str)
    parser.add_argument("-l", "--log-file", metavar="log_file", dest="log_file", type=str, default=None,
                        help="path to log file")
    parser.add_argument("-L", "--log-level", dest="log_level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR',
                                                                        'CRITICAL'], default="INFO",
                        help="set the logging level")
    parser.add_argument("-d", "--from-date", metavar="from_date", dest="from_date", type=str,
                        help="use only articles included in WB at or after the specified date")
    parser.add_argument("-m", "--max-num-papers", metavar="max_num_papers", dest="max_num_papers", type=int)

    args = parser.parse_args()
    logging.basicConfig(filename=args.log_file, level=args.log_level,
                        format='%(asctime)s - %(name)s - %(levelname)s:%(message)s')

    cm = CorpusManager()
    db_manager = WBDBManager(dbname=args.db_name, user=args.db_user, password=args.db_password, host=args.db_host)
    with db_manager.generic.get_cursor() as curs:
        curs.execute("SELECT trp_paper FROM trp_peper")
        already_processed = {papid.replace("\"", "") for row in curs.fetchall() for papid in row[0].split(",")}
    cm.load_from_wb_database(
        db_name=args.db_name, db_user=args.db_user, db_password=args.db_password, db_host=args.db_host,
        from_date=args.from_date, max_num_papers=args.max_num_papers,
        exclude_ids=list(already_processed),
        pap_types=["Journal_article"], exclude_temp_pdf=True)
    logger.info("Finished loading papers from DB")
    known_transgenes = db_manager.generic.get_curated_transgenes(exclude_id_used_as_name=True, exclude_invalid=True)
    transgene_papers = defaultdict(list)
    for paper in cm.get_all_papers():
        logger.info("Extracting transgene info from paper " + paper.paper_id)
        sentences = paper.get_text_docs(include_supplemental=True, split_sentences=True, lowercase=False)
        matches = set()
        for sentence in sentences:
            sentence = sentence.replace('–', '-')
            sentence = sentence.replace('‐', '-')

            for transgene in known_transgenes:
                escaped_transgene = re.escape(transgene)
                start_match = re.match(r'^{}[\s:,;.]'.format(escaped_transgene), sentence)

                # Match transgene in the middle of the sentence
                middle_match = re.search(r'(?<=\s|^){}(?=[\s:,;.]|$)'.format(escaped_transgene), sentence)

                # Match transgene at the end of the sentence
                end_match = re.search(r'(?<=\s){}\.$'.format(escaped_transgene), sentence)

                # Match transgene with optional parentheses
                paren_match = re.search(r'\(?{}(?:[),]|\)?)'.format(escaped_transgene), sentence)

                if start_match or middle_match or end_match or paren_match:
                    matches.add(transgene)
        for match in matches:
            transgene_papers[match].append(paper.paper_id)
    for transgene_name, paper_ids in transgene_papers.items():
        with db_manager.generic.get_cursor() as curs:
            res = curs.execute("SELECT id FROM trp_transgene WHERE trp_transgene = %s", (transgene_name,))
            transgene_id = res.fetchone()
            curs.execute("DELETE FROM trp_paper WHERE joinkey = %s", (transgene_id,))
            curs.execute("INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
                         (transgene_id, ",".join(["\"" + pap_id + "\"" for pap_id in paper_ids])))
            curs.execute("INSERT INTO trp_paper_hst (joinkey, trp_paper) VALUES (%s, %s)",
                         (transgene_id, ",".join(["\"" + pap_id + "\"" for pap_id in paper_ids])))
    logger.info("Finished")


if __name__ == '__main__':
    main()
