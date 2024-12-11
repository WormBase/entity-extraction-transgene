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
        curs.execute("SELECT trp_paper FROM trp_paper")
        already_processed = {papid.replace("\"", "") for row in curs.fetchall() for papid in row[0].split(",")}
    cm.load_from_wb_database(
        db_name=args.db_name, db_user=args.db_user, db_password=args.db_password, db_host=args.db_host,
        from_date=args.from_date, max_num_papers=args.max_num_papers,
        exclude_ids=list(already_processed),
        pap_types=["Journal_article"], exclude_temp_pdf=True)
    logger.info("Finished loading papers from DB")
    known_transgenes = db_manager.generic.get_curated_transgenes(exclude_id_used_as_name=True, exclude_invalid=True)
    known_transgenes = set(known_transgenes)
    unknown_transgene_papers = defaultdict(set)
    transgene_papers = defaultdict(set)
    for paper in cm.get_all_papers():
        logger.info("Extracting transgene info from paper " + paper.paper_id)
        sentences = paper.get_text_docs(include_supplemental=True, split_sentences=True, lowercase=False)
        for sentence in sentences:
            sentence = sentence.replace('–', '-')
            sentence = sentence.replace('‐', '-')

            for transgene in known_transgenes:
                escaped_transgene = re.escape(transgene)
                start_match = re.match(r'^{}[\s:,;.]'.format(escaped_transgene), sentence)

                # Match transgene in the middle of the sentence
                middle_match = re.search(r'(^|\s){}(?=[\s:,;.]|$)'.format(escaped_transgene), sentence)

                # Match transgene at the end of the sentence
                end_match = re.search(r'{}[\s:,;.!?]?(\s|$)'.format(escaped_transgene), sentence)

                # Match transgene with optional parentheses
                paren_match = re.search(r'\(?{}(?:[),]|\)?)'.format(escaped_transgene), sentence)

                if start_match or middle_match or end_match or paren_match:
                    transgene_papers[transgene].add(paper.paper_id)

            unknown_matches = re.findall(r'\b([a-z]{1,3}(Is|In|Si|Ex)[0-9]+[a-z]?)\b', sentence, re.IGNORECASE)
            for match in unknown_matches:
                if match[0].lower() not in known_transgenes:
                    unknown_transgene_papers[match[0]].add(paper.paper_id)

    for transgene_name, paper_ids in transgene_papers.items():
        with db_manager.generic.get_cursor() as curs:
            res = curs.execute("SELECT id FROM trp_transgene WHERE trp_transgene = %s", (transgene_name,))
            transgene_id = res.fetchone()
            curs.execute("DELETE FROM trp_paper WHERE joinkey = %s", (transgene_id,))
            curs.execute("INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
                         (transgene_id, ",".join(["\"" + pap_id + "\"" for pap_id in paper_ids])))
            curs.execute("INSERT INTO trp_paper_hst (joinkey, trp_paper) VALUES (%s, %s)",
                         (transgene_id, ",".join(["\"" + pap_id + "\"" for pap_id in paper_ids])))

    # Process unknown transgenes
    for transgene_name, paper_ids in unknown_transgene_papers.items():
        with db_manager.generic.get_cursor() as curs:
            # Generate new WBTransgene ID
            curs.execute("SELECT MAX(joinkey) FROM trp_name")
            max_id = curs.fetchone()[0]
            new_id = max_id + 1 if max_id else 1
            new_wbtransgene_id = f"WBTransgene{new_id:08d}"

            # Insert into trp_name
            curs.execute("INSERT INTO trp_name (id, object) VALUES (%s, %s)", (new_id, new_wbtransgene_id))

            # Insert into trp_publicname
            curs.execute("INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
                         (new_id, transgene_name))

            # Insert into trp_paper
            paper_ids_str = ",".join([f"\"{pid}\"" for pid in paper_ids])
            curs.execute("INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)", (new_id, paper_ids_str))

            # Insert into trp_curator
            curs.execute("INSERT INTO trp_curator (joinkey, trp_curator) VALUES (%s, 'WBPerson4793')", (new_id,))

            # Update history tables
            curs.execute("INSERT INTO trp_name_hst (id, object) VALUES (%s, %s)", (new_id, new_wbtransgene_id))
            curs.execute("INSERT INTO trp_publicname_hst (joinkey, trp_publicname) VALUES (%s, %s)",
                         (new_id, transgene_name))
            curs.execute("INSERT INTO trp_paper_hst (joinkey, trp_paper) VALUES (%s, %s)", (new_id, paper_ids_str))
            curs.execute("INSERT INTO trp_curator_hst (joinkey, trp_curator) VALUES (%s, 'WBPerson4793')",
                         (new_id,))

        logger.info("Finished processing all transgenes")

    logger.info("Finished")


if __name__ == '__main__':
    main()
