# README

L'archive "francearchives_commemorations_<date>.zip" contient les dumps des données des commémorations du site https://francearchives.fr/ aux formats suivants :

1. `<table_name>_pg` : dumps PostgreSQL permettant l'import via `pg_restore` ;

2. `<table_name>.csv` : dumps CSV.

L'arborescence de l'archive est la suivante :

```.
├── commemo_agent_dump.csv
├── commemo_agent_dump_pg
│   ├── 4149.dat.gz
│   └── toc.dat
├── commemo_collection_dump.csv
├── commemo_collection_dump_pg
│   ├── 4150.dat.gz
│   └── toc.dat
├── commemo_dates_dump.csv
├── commemo_dates_dump_pg
│   ├── 4151.dat.gz
│   └── toc.dat
├── commemo_dump_csv.csv
├── commemo_dump_pg
│   ├── 4152.dat.gz
│   └── toc.dat
├── commemo_images_dump.csv
├── commemo_images_dump_pg
│   ├── 4151.dat.gz
│   └── toc.dat
├── commemo_collection_images_dump.csv
├── commemo_collection_images_dump_pg
│   ├── 4150.dat.gz
│   └── toc.dat
├── commemo_programm_dump.csv
├── commemo_programm_dump_pg
│   ├── 4150.dat.gz
│   └── toc.dat
├── commemo_programm_files_dump.csv
├── commemo_programm_files_dump_pg
│   ├── 4149.dat.gz
│   └── toc.dat
├── files
│   ├── commemo_content_1234567890.txt
│   └── image.svg
└── README.md
```

Pour chacun des deux formats 8 tables sont générées :

1. *commemo_collection_dump[.csv/_pg]* contient les données des
collections qui regroupent des commémorations par année. Une
commémoration appartient toujours à une seule collection, mais une
collection peut regrouper plusieurs commémorations.

2. *commemo_dump[_csv.csv/_pg]* contient les données des commémorations.

  2.1 format CSV : la colonne *file* contient le chemin relatif vers
  un fichier avec contenu de la commémoration exporté dans le répertoire *files* de l'archive ;

  2.2 format Postgres : la colonne *file* contient le path vers le
  fichier avec le contenu de la commémoration ;

3. *commemo_dates_dump[.csv/_pg]* contient les métadonnées des dates des commémorations.

4. *commemo_collection_images_dump[.csv/_pg]* contient les métadonnées des images
des collections de commémorations, et notamment, les chemins relatifs des images
exportées dans le répertoire *files* de l'archive.

5. *commemo_images_dump[.csv/_pg]* contient les métadonnées des images
des commémorations, et notamment, les chemins relatifs des images
exportées dans le répertoire *files* de l'archive.

6. *commemo_programm_dump[.csv/_pg]* contient les programmes de chaque commémoration.

7. *commemo_programm_files_dump[.csv/_pg]* contient les fichiers liés aux programmes
des commémorations et les chemins relatifs des fichiers exportés dans le répertoire
*files* de l'archive.

8. *commemo_agent_dump[.csv/_pg]* contient les index (autorités) des commémorations.

## Import Postgres

Comme une partie des tables contient des clés étrangères, elles doivent être réimportées dans l'ordre suivant :

1. *commemo_collection_dump_pg
2. *commemo_collection_images_dump_pg
3. *commemo_programm_dump_pg
4. *commemo_programm_files_dump_pg
5. *commemo_dump_pg
6. *commemo_images_dump_pg
7. *commemo_agent_dump_pg
8. *commemo_dates_dump_pg


Pour restaurer les données postgres utilisez les commandes ci-dessous :

```$ cat <<\EOF>> restore_commemo_pg.sh
#!/bin/bash

DUMPS=(
    "commemo_collection_dump_pg" \
    "commemo_collection_images_dump_pg" \
    "commemo_programm_dump_pg" \
    "commemo_programm_files_dump_pg" \
    "commemo_dump_pg" "commemo_images_dump_pg" \
    "commemo_agent_dump_pg" \
    "commemo_dates_dump_pg"
);

for DUMP in ${DUMPS[*]}; do
    echo "restoring $DUMP to $1";
    pg_restore -F d -d "$1" "$2/$DUMP";
done

EOF
```

$ cat > . restore_commemo_pg.sh <db_name> <path_to_unzipped_archive>
