Summary
=======

Cube applicatif pour FranceArchives https://francearchives.fr/

Ce cube utilise le framework CubicWeb https://www.cubicweb.org/

Les dépendances sont décrites dans le packaging python (`__pkginfo__.py`) et
javascript (`package.json`).


Licence
-------

cubicweb-francearchives est publié sous les termes de la licence CeCiLL v2.

La licence complète peut être trouvée dans ce dépot `LICENCE.txt` et
https://cecill.info/licences/Licence_CeCILL_V2.1-fr.html


Description du projet FranceArchives
------------------------------------

Le projet FranceArchives repose sur 2 cubes:

- cubicweb-francearchives, le cube de consultation.

- cubicweb-frarchives-edition, le cube d'édition (CMS), il dépend du cube de
  consultation et contient les mécanismes propres à la partie gestion de données
  de l'application FranceArchives.

De la même manière, deux instances sont déployées en production :

- instance de consultation, une instance de cubicweb-francearchives, qui permet
  toutes les fonctionnalités de recherche, consultation des ressources publiées,
  etc. sur le site FranceArchives.

- instance d'édition, une instance de cubicweb-frarchives-edition, qui permet
  d'éditer, d'importer des données, de rechercher et visualiser toutes les
  ressources de la base de données (publiées ou non).

Lors du développement sur FranceArchives, il est utile d'avoir les 2 instances
en parallèle pour vérifier que les développements faits sur un des deux cubes
fonctionnent comme souhaité sur les deux instances.

Dans cette documentation, nous présentons la manière d'installer tout d'abord
l'instance d'édition puis l'instance de consultation.

Installation de l'environnement de développement du projet FranceArchives
=========================================================================

Mise en place de l'environnement (virtualenv)
---------------------------------------------

Installer par pip install dans un  virtualenv ou avec l'image Docker.

* https://hub.docker.com/r/francearchives/cubicweb-francearchives
* https://hub.docker.com/r/francearchives/cubicweb-frarchives-edition

Installation de redis
---------------------

L'instance va nécessiter un serveur redis sur votre ordinateur. https://redis.io/docs/latest/operate/oss_and_stack/install/install-redis/install-redis-on-linux/


Utiliser S3Storage en local
---------------------------

Installer minio https://min.io/download#/linux

Créer le bucket pour francearchives ::

     $ mkdir -p <path minio>/minio/${AWS_S3_BUCKET_NAME}

Ajouter les variables d'environnement pour le cube : pour plus de praticité,
les lignes suivantes peuvent être ajoutées au fichier bin/activate de votre
virtualenv (.fa-venv/bin/activate) ::

    $ export AWS_S3_ENDPOINT_URL=http://127.0.0.1:9000
    $ export AWS_ACCESS_KEY_ID=<minio>
    $ export AWS_SECRET_ACCESS_KEY=<miniosecret>
    $ export AWS_S3_BUCKET_NAME=<francearchives>


Lancer le serveur minio ::

    $ export MINIO_ROOT_USER=<minio>
    $ export MINIO_ROOT_PASSWORD=<miniosecret>
    $ minio server <path minio>/minio

Vous pouvez accéder à minio sur http://127.0.0.1:9000/minio/login

Installer ElasticSearch
-----------------------

Pour fonctionner, votre instance aura besoin d'un serveur elasticsearch sur votre
machine. Il peut être lancé depuis une installation locale
(voir https://www.elastic.co/guide/en/elasticsearch/reference/current/install-elasticsearch.html)
ou via une image docker.

Initialisation d'une instance CMS
---------------------------------

Nous allons créer une instance du cube frarchives_edition *avec un utilisateur
anonyme*. Donc, activer le virtualenv, puis :

::

    (fa-venv)$ cubicweb-ctl create frarchives_edition atelier

Attention à porter sur la configuration de l'instance lorsque la commande précédente
est lancée.

Mot de passe admin
~~~~~~~~~~~~~~~~~~

Lors de la création de la base, il y une vérification de la sécurité du mot de
passe admin.
Il doit contenir au moins 12 caractères et être composé de majuscules, minuscules,
chiffres et caractères spéciaux.

Si vous possédez un dump d'une base FranceArchives
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Si vous possédez un dump d'une base FranceArchives, ne créez pas la base
(Répondre non à la question "Run db-create to create the system database ?")

Note : Commande pour créer un dump postgres d'une base de données

::

    pg_dump -v --no-owner -Fc atelier > dump_atelier

Note : Commande pour initialiser une base de données à partir du dump généré
par la commande précédente

::

    pg_restore --no-owner -Fc -d atelier dump_atelier

Il vous faudra ensuite réinitialiser le mot de passe admin de votre instance

::

    (fa-venv)$ cubicweb-ctl reset-admin-pwd atelier

Si vous voulez partir d'une base vide
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Vous pouvez lancer la commande db-create lors de la création de l'instance.

Configuration pyramid
~~~~~~~~~~~~~~~~~~~~~

Il faut installer un fichier ``pyramid.ini`` dans le répertoire de
l'instance (par ex. ``~/etc/cubicweb.d/atelier/`` contenant) :

::
[main]

cubicweb.auth.authtkt.session.secret = stuff
cubicweb.auth.authtkt.persistent.secret = stuff
cubicweb.auth.authtkt.session.secure = yes
cubicweb.auth.authtkt.persistent.secure = yes
cubicweb.auth.authtkt.session.timeout = 3600
cubicweb.auth.authtkt.session.samesite = Strict
cubicweb.pyramid.enable_csrf=no

cubicweb.includes =
      cubicweb.pyramid.auth
      cubicweb_frarchives_edition.cms
      cubicweb.pyramid.rest_api.include_rdf
            # cubicweb_api

pyramid.includes =
      # pyramid_debugtoolbar
      pyramid_session_redis

#  pyramid_debugtoolbar
redis.sessions.timeout = 1200
redis.sessions.secret = stuff
redis.sessions.prefix = pniacms:
redis.sessions.url = redis://localhost:6379/0
rq.redis_url = redis://localhost:6379/

# cubicweb.auth.authtkt.session.samesite = Strict
cubicweb.auth.authtkt.session.reissue_time = 42300
cubicweb.auth.authtkt.session.max_age = 42300
cubicweb.auth.authtkt.persistent.timeout = 42300
cubicweb.auth.authtkt.persistent.reissue_time = 42300


Configuration CubicWeb
~~~~~~~~~~~~~~~~~~~~~~

Copier le contenu du fichier `./doc/all-in-one.conf.example` dans le fichier de configuration
de votre instance: `~/etc/cubicweb.d/atelier/all-in-one.conf`

Installer et compiler le JavaScript
-----------------------------------

Dans chaque projet (cubicweb-francearchives et cubicweb-frarchives-edition),
lancer les commandes suivantes ::

    npm ci
    npm run build

Pour avoir un build continu ::

    npm run watch


Compilier les css
-----------------

Il est nécessaire d'utiliser le paquet ``sass`` avec npx.

1. Pour compiler la feuille des styles unique utiliser la commande suivante dans le
::

  npx sass scss/main.scss:cubicweb_francearchives/data/css/francearchives.bundle.css

2. Utiliser -watch pour tenir compte des modifications :

::

  npx sass --watch scss/main.scss:cubicweb_francearchives/data/css/francearchives.bundle.css

Si vous tombez sur l'erreur suivante ::

  >>> Sass is watching for changes. Press Ctrl-C to stop.
  LoadError: cannot load such file -- sass-listen

installer le packet `sass-listen` peut aider à resoudre le problème ::

  $ sudo gem install sass-listen

Remplir les champs de traduction
--------------------------------

Pour gérer la traduction, lancez la commande :

::

    (fa-env)$ cubicweb-ctl i18ninstance atelier


Démarrer l'instance
-------------------

Vous y êtes presque !! 

Avant de lancer votre instance, n'oubliez pas d'avoir :
- votre serveur minio qui tourne (voir section sur Minio)
- un serveur elasticsearch qui tourne

::

    (fa-env)$ cubicweb-ctl start -D atelier


Démarrer un worker
------------------

Pour exécuter les tâches asynchrones (comme l'import de fichiers EAD, etc.)
on utilise un worker RQ, à lancer en parallèle de l'application pyramid.

::

    (fa-env)$ cubicweb-ctl rq-worker atelier


Remplir ses index elasticsearch
-------------------------------

Si vous êtes partis d'une base existante (dump PostGres), vous allez devoir
indexer vos données dans les index elasticsearch.

Indexer les documents :

::

    (fa-env)$ cubicweb-ctl index-in-es atelier


Indexer les autorités :

::

    (fa-env)$ cubicweb-ctl index-es-suggest atelier

Indexer les données nominatives :

::

    (fa-env)$ cubicweb-ctl index-es-nomina atelier



Configurer son instance de consultation
=======================================

En production, deux instances fonctionnent en parallèle : une de type CMS (que l'on
a appelée atelier dans les étapes précédentes). Il peut ête utile d'avoir
également sous la main une instance consultation.

Activer le virtualenv puis ::

    (fa-venv)$ cubicweb-ctl create francearchives consultation

Cette instance va utiliser le namespace "published" de l'instance atelier.
Il ne faut donc pas lancer la commande db-create.

Fichier sources
---------------

Modifier le fichier ~/etc/cubicweb.d/consultation/sources pour y
ajouter/modifier les informations suivantes ::

    db-name=atelier

    db-namespace=published

Fichier all-in-one.conf
-----------------------

Copier le contenu du fichier `./doc/consultation_all-in-one.conf.example` dans le fichier de configuration
de votre instance: `~/etc/cubicweb.d/consultation/all-in-one.conf`

Fichier pyramid.ini
-------------------

Copier la configuration suivante dans le fichier `~/etc/cubicweb.d/consultation/pyramid.ini`

::

    [main]
    cubicweb.auth.authtkt.session.secret = stuff
    cubicweb.auth.authtkt.persistent.secret = stuff
    cubicweb.auth.authtkt.session.secure = no
    cubicweb.auth.authtkt.persistent.secure = no
    cubicweb.session.secret = the-secret

    cubicweb.bwcompat = no
    cubicweb.defaults = no

    cubicweb.includes =
        cubicweb.pyramid.auth
        cubicweb.pyramid.session

Remplir les champs de traduction
--------------------------------

Pour gérer la traduction dans cette instance, lancez la commande :

::

    (fa-env)$ cubicweb-ctl i18ninstance consultation


Lancer l'instance de consultation
---------------------------------

L'instance de consultation se lance comme l'instance CMS :
Avant de lancer votre instance, n'oubliez pas d'avoir :
- votre serveur minio qui tourne (voir section sur Minio)
- un serveur elasticsearch qui tourne

::

    (fa-env)$ cubicweb-ctl start -D consultation


Bonnes pratiques de développement
=================================


Black
-----

Pour lancer **black** ::

  black --config pyproject.toml .

Ajouter **black** dans les hooks **hg** ::

créer le script `path_hook` (exemple de code) ::

  #!/bin/sh
  for fpath in $(hg status --no-status --modified --added | grep ".py$") ; do
    black ${fpath}
  done

et appeler le ̀.hg\hgrc` du projet ::

  [hooks]
  precommit = path_to_hook
  pre-amend = path_to_hook


il est possible d'intégrer la config utilisée pour le projet ::

  #!/bin/sh
  for fpath in $(hg status --no-status --modified --added | grep ".py$") ; do
    black --config $1 ${fpath}
  done


et appeler le ̀.hg\hgrc` du projet ::

  [hooks]
  precommit = path_to_hook pyproject.toml
  pre-amend = path_to_hook pyproject.toml


Tests
-----

Lancer les tests avec tox
~~~~~~~~~~~~~~~~~~~~~~~~~

Vous aurez besoin de :

* elasticsearch version 7.x installable en suivant ce guide https://www.elastic.co/guide/en/elasticsearch/reference/current/getting-started-install.html
* ``sudo apt-get install poppler-utils`` (pour ``pdftotext``)
* ``sudo apt-get install ruby-sass`` (pour ``sass``)

Pour lancer les tests ::

  tox

Pour lancer les tests en parallèle sur plusieurs CPUs, installez `pytest-xdist`.

Les données utilisées pour les tests ne correspondent pas aux données
réelles.

Ces fichiers ne doivent pas être utilisés dans un autre but que celui
de tester la présente application. Le ministère de la Culture décline
toute responsabilité sur les problèmes et inconvénients, de quelque
nature qu'ils soient, qui pourraient survenir en raison d'une
utilisation de ces fichiers à d'autres fins que de tester la présente
application.

**ElasticSearch et Pifpaf**

``pifpaf`` est utilisé pour permettre à ``tox`` de se servir des services installés en
local. Pour que ``pifpaf`` arrive à lancer ``elasticsearch`` il faut ::

 1. Ajouter le compte utilisateur servant a lancer ``tox`` au groupe ``elasticsearch``::

    usermod -a -G elasticsearch USER

 2. Modifier les permissions de `/etc/elasticsearch` ::

    chmod +rx /etc/elasticsearch
    chmod -R +r /etc/elasticsearch
    chmod +r /etc/default/elasticsearch

 3. Modifier les permissions du dossier ``/var/log/elasticsearch``::

    chmod 774 /var/log/elasticsearch

 4. Modifier les permissions du fichier ``/var/log/elasticsearch/gc.log``::

    chown USER /var/log/elasticsearch/gc.log
    chmod 664 /var/log/elasticsearch/gc.log

Lancer les tests a11y
~~~~~~~~~~~~~~~~~~~~~

1. Installer pa11y

   npm install pa11y

2. Lancer les tests

   BASEURL=<host:port>/fr  node a11y/test.js


Contributrices et contributeurs
-------------------------------

Voici une liste non exhaustive des personnes ayant contribué à
ce logiciel (ordre alphabetique) :

* Adrien Di Mascio
* Arthur Lutz
* Carine Dengler
* David Douard
* Elodie Thiéblin
* Juliette Belin
* Katia Saurfelt
* Samuel Trégouët
* Sylvain Thénault
* Tanguy Le Carrour
