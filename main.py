import argparse
import datetime
import logging
import os
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
    parser.add_argument("-f", "--processed-files-path", metavar="processed_files_path",
                        dest="processed_files_path", type=str,
                        default=None, help="path to files with processed WBPaper IDs")

    args = parser.parse_args()
    logging.basicConfig(filename=args.log_file, level=args.log_level,
                        format='%(asctime)s - %(name)s - %(levelname)s:%(message)s')

    script_processed = set()
    if args.processed_files_path is not None:
        os.makedirs(args.processed_files_path, exist_ok=True)
        for f in os.listdir(args.processed_files_path):
            if os.path.isfile(os.path.join(args.processed_files_path, f)):
                script_processed.update({line.strip() for line in open(os.path.join(args.processed_files_path, f))})

    cm = CorpusManager()
    db_manager = WBDBManager(dbname=args.db_name, user=args.db_user, password=args.db_password, host=args.db_host)

    with db_manager.generic.get_cursor() as curs:
        curs.execute("SELECT trp_paper FROM trp_paper")
        already_processed = {papid.replace("\"", "") for row in curs.fetchall() for papid in row[0].split(",")}

    all_proceesed = already_processed | script_processed
    logger.debug(f"Number of already processed papers: {str(len(already_processed))}")
    cm.load_from_wb_database(
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password,
        db_host=args.db_host,
        from_date=args.from_date,
        max_num_papers=args.max_num_papers,
        exclude_ids=list(all_proceesed),
        pap_types=["Journal_article"],
        exclude_temp_pdf=True)

    logger.info("Finished loading papers from DB")
    logger.debug(f"Number of papers in the selected corpus: {str(cm.size())}")
    known_transgenes = db_manager.generic.get_curated_transgenes(exclude_id_used_as_name=True, exclude_invalid=True)
    known_transgenes = set(known_transgenes)

    logger.debug(f"Number of known transgenes: {str(len(known_transgenes))}")

    transgene_pattern = re.compile(r'\b([a-z]{1,3}(Is|In|Si|Ex)[0-9]+[a-z]?)\b', re.IGNORECASE)
    known_transgenes_pattern = {re.compile(r'(^|\s){}(?=[\s:,;.]|$)'.format(re.escape(transgene))) for transgene in
                                known_transgenes}

    transgene_papers = defaultdict(set)
    unknown_transgenes_to_add = set()
    processed_ids = []

    for paper in cm.get_all_papers():
        logger.info("Extracting transgene info from paper " + paper.paper_id)
        # Concatenate all sentences with double spaces
        sentences = paper.get_text_docs(include_supplemental=True, split_sentences=True, lowercase=False)
        concatenated_text = '  '.join(sentence.replace('–', '-').replace('‐', '-') for sentence in sentences)

        # Extract known transgenes
        for pattern in known_transgenes_pattern:
            for match in pattern.finditer(concatenated_text):
                transgene_name = match.group(0).strip()
                transgene_papers[transgene_name].add(paper.paper_id)

        # Extract unknown transgenes
        for match in transgene_pattern.finditer(concatenated_text):
            transgene = match.group(0)
            if transgene not in known_transgenes:
                unknown_transgenes_to_add.add(transgene)
                transgene_papers[transgene].add(paper.paper_id)

        processed_ids.append(paper.paper_id)

    # add unknown transgenes to db
    with db_manager.generic.get_cursor() as curs:
        curs.execute("SELECT MAX(joinkey::int) FROM trp_name")
        max_id = int(curs.fetchone()[0])
        new_id = max_id if max_id else 0
        for transgene_name in unknown_transgenes_to_add:
            # Generate new WBTransgene ID
            new_id = new_id + 1
            new_wbtransgene_id = f"WBTransgene{new_id:08d}"

            # Insert into trp_name
            curs.execute("INSERT INTO trp_name (joinkey, trp_name) VALUES (%s, %s)", (new_id, new_wbtransgene_id))

            # Insert into trp_publicname
            curs.execute("INSERT INTO trp_publicname (joinkey, trp_publicname) VALUES (%s, %s)",
                         (new_id, transgene_name))

            # Insert into trp_curator
            curs.execute("INSERT INTO trp_curator (joinkey, trp_curator) VALUES (%s, 'WBPerson4793')", (new_id,))

            # Update history tables
            curs.execute("INSERT INTO trp_name_hst (joinkey, trp_name_hst) VALUES (%s, %s)",
                         (new_id, new_wbtransgene_id))
            curs.execute("INSERT INTO trp_publicname_hst (joinkey, trp_publicname_hst) VALUES (%s, %s)",
                         (new_id, transgene_name))
            curs.execute("INSERT INTO trp_curator_hst (joinkey, trp_curator_hst) VALUES (%s, 'WBPerson4793')",
                         (new_id,))

    # Add transgenes to trp_paper
    for transgene_name, paper_ids in transgene_papers.items():
        with db_manager.generic.get_cursor() as curs:
            curs.execute("SELECT joinkey FROM trp_publicname WHERE trp_publicname = %s", (transgene_name,))
            transgene_id = curs.fetchone()
            curs.execute("DELETE FROM trp_paper WHERE joinkey = %s", (transgene_id,))
            curs.execute("INSERT INTO trp_paper (joinkey, trp_paper) VALUES (%s, %s)",
                         (transgene_id, ",".join([f"\"{pap_id}\"" for pap_id in paper_ids])))
            curs.execute("INSERT INTO trp_paper_hst (joinkey, trp_paper_hst) VALUES (%s, %s)",
                         (transgene_id, ",".join([f"\"{pap_id}\"" for pap_id in paper_ids])))

    # Write processed paper IDs back to file
    if args.processed_files_path is not None:
        file_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_results.csv"
        with open(os.path.join(args.processed_files_path, file_name), 'w') as f:
            for paper_id in processed_ids:
                f.write(f"{paper_id}\n")

    logger.info("Finished")


if __name__ == '__main__':
    main()
