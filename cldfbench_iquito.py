from collections import ChainMap
import pathlib
import re

from cldfbench import CLDFSpec, Dataset as BaseDataset

from pybtex.database import parse_string
from pydictionaria.preprocess_lib import (
    marker_fallback_sense, marker_fallback_entry, merge_markers
)
from pydictionaria.sfm_lib import Database as SFM
from pydictionaria import sfm2cldf


def reorganize(sfm):
    """Use this function if you need to manually add or remove entrys from the
    SFM data.

    Takes an SFM database as an argument and returns a modified SFM database.
    """
    return sfm


def merged_va(marker_dict):
    va = marker_dict.get('va') or ''
    vet = marker_dict.get('vet') or ''
    if va and vet:
        return '{}: {}'.format(vet, va)
    else:
        return va


def no_irregular_plural(pair):
    k, v = pair
    return (
        k != 'va'
        or not v.startswith('irregular plural:'))


def preprocess(entry):
    """Use this function if you need to change the contents of an entry before
    any other processing.

    This is run on every entry in the SFM database.
    """
    if 'EXCLUDE' in (entry.get('z6') or ''):
        return False

    entry = marker_fallback_sense(entry, 'de', 'ge')
    entry = marker_fallback_sense(entry, 'd_Spn', 'g_Spn')
    entry = marker_fallback_entry(entry, 'lx', 'lx_notused')

    entry = merge_markers(entry, ['va', 'vet'], 'va', format_fn=merged_va)

    entry = entry.__class__(filter(no_irregular_plural, entry))
    return entry


def authors_string(authors):
    """Return formatted string of all authors."""
    def is_primary(a):
        return not isinstance(a, dict) or a.get('primary', True)

    primary = ' and '.join(
        a['name'] if isinstance(a, dict) else a
        for a in authors
        if is_primary(a))
    secondary = ' and '.join(
        a['name']
        for a in authors
        if not is_primary(a))
    if primary and secondary:
        return '{} with {}'.format(primary, secondary)
    else:
        return primary or secondary


def _detex(v):
    v = re.sub(r'\{\\iqt\s+([^}]*)\}', r'<\1>', v)
    v = re.sub(r'\{\\sp\s+([^}]*)\}', r'???\1???', v)
    v = re.sub(r'\\textit\s*\{\s*([^}]*)\}', r'\1', v)
    v = v.replace('~', ' ')
    return v


def detex(v):
    if isinstance(v, list):
        return [_detex(e) for e in v]
    else:
        return _detex(v)


class Dataset(BaseDataset):
    dir = pathlib.Path(__file__).parent
    id = "iquito"

    def cldf_specs(self):  # A dataset must declare all CLDF sets it creates.
        return CLDFSpec(
            dir=self.cldf_dir,
            module='Dictionary',
            metadata_fname='cldf-metadata.json')

    def cmd_download(self, args):
        """
        Download files to the raw/ directory. You can use helpers methods of `self.raw_dir`, e.g.

        >>> self.raw_dir.download(url, fname)
        """
        pass

    def cmd_makecldf(self, args):
        """
        Convert the raw data to a CLDF dataset.

        >>> args.writer.objects['LanguageTable'].append(...)
        """

        # read data

        md = self.etc_dir.read_json('md.json')
        properties = md.get('properties') or {}
        language_name = md['language']['name']
        isocode = md['language']['isocode']
        language_id = md['language']['isocode']
        glottocode = md['language']['glottocode']

        marker_map = ChainMap(
            properties.get('marker_map') or {},
            sfm2cldf.DEFAULT_MARKER_MAP)
        entry_sep = properties.get('entry_sep') or sfm2cldf.DEFAULT_ENTRY_SEP
        sfm = SFM(
            self.raw_dir / 'db.sfm',
            marker_map=marker_map,
            entry_sep=entry_sep)

        examples = sfm2cldf.load_examples(self.raw_dir / 'examples.sfm')

        if (self.raw_dir / 'sources.bib').exists():
            sources = parse_string(self.raw_dir.read('sources.bib'), 'bibtex')
        else:
            sources = None

        if (self.etc_dir / 'cdstar.json').exists():
            media_catalog = self.etc_dir.read_json('cdstar.json')
        else:
            media_catalog = {}

        # preprocessing

        sfm = reorganize(sfm)
        sfm.visit(preprocess)

        # processing

        with open(self.dir / 'cldf.log', 'w', encoding='utf-8') as log_file:
            log_name = '%s.cldf' % language_id
            cldf_log = sfm2cldf.make_log(log_name, log_file)

            entries, senses, examples, media = sfm2cldf.process_dataset(
                self.id, language_id, properties,
                sfm, examples, media_catalog=media_catalog,
                glosses_path=self.raw_dir / 'glosses.flextext',
                examples_log_path=self.dir / 'examples.log',
                glosses_log_path=self.dir / 'glosses.log',
                cldf_log=cldf_log)

            # Note: If you want to manipulate the generated CLDF tables before
            # writing them to disk, this would be a good place to do it.

            # cldf schema

            sfm2cldf.make_cldf_schema(
                args.writer.cldf, properties,
                entries, senses, examples, media)

            sfm2cldf.attach_column_titles(args.writer.cldf, properties)

            entries = [{k: detex(v) for k, v in e.items()} for e in entries]
            senses = [{k: detex(v) for k, v in e.items()} for e in senses]
            examples = [{k: detex(v) for k, v in e.items()} for e in examples]
            media = [{k: detex(v) for k, v in e.items()} for e in media]

            print(file=log_file)

            entries = sfm2cldf.ensure_required_columns(
                args.writer.cldf, 'EntryTable', entries, cldf_log)
            senses = sfm2cldf.ensure_required_columns(
                args.writer.cldf, 'SenseTable', senses, cldf_log)
            examples = sfm2cldf.ensure_required_columns(
                args.writer.cldf, 'ExampleTable', examples, cldf_log)
            media = sfm2cldf.ensure_required_columns(
                args.writer.cldf, 'media.csv', media, cldf_log)

            entries = sfm2cldf.remove_senseless_entries(
                senses, entries, cldf_log)

        # output

        if sources:
            args.writer.cldf.add_sources(sources)
        args.writer.cldf.properties['dc:creator'] = authors_string(
            md.get('authors') or ())

        language = {
            'ID': language_id,
            'Name': language_name,
            'ISO639P3code': isocode,
            'Glottocode': glottocode,
        }
        args.writer.objects['LanguageTable'] = [language]

        args.writer.objects['EntryTable'] = entries
        args.writer.objects['SenseTable'] = senses
        args.writer.objects['ExampleTable'] = examples
        args.writer.objects['media.csv'] = media
