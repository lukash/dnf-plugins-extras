# Copyright (C) 2013-2014  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#

from __future__ import absolute_import
from __future__ import unicode_literals

import dnf
import logging
import os
from tests import support
import tempfile
import unittest

from tests.support import mock

import kickstart
import pykickstart


class _KickstartFileFixture(object):
    """Test fixture containing a kickstart file."""

    KICKSTART_GROUP = 'group'

    KICKSTART_PACKAGE = 'package'

    @classmethod
    def _create_kickstart(cls):
        """Create a kickstart file and return its path."""
        with tempfile.NamedTemporaryFile('wt', delete=False) as file_:
            file_.write('%packages\n')
            if cls.KICKSTART_PACKAGE:
                file_.write('%s\n' % cls.KICKSTART_PACKAGE)
            if cls.KICKSTART_GROUP:
                file_.write('@%s\n' % cls.KICKSTART_GROUP)
            file_.write('%end\n')
        return file_.name

    @classmethod
    def setUpClass(cls):
        """Prepare the test fixture."""
        super(_KickstartFileFixture, cls).setUpClass()
        cls._path = cls._create_kickstart()

    @classmethod
    def tearDownClass(cls):
        """Tear down the test fixture."""
        super(_KickstartFileFixture, cls).tearDownClass()
        os.remove(cls._path)

class _KickstartCommandFixture(_KickstartFileFixture):
    """Test fixture containing a `kickstart.KickstartCommand` instance."""

    KICKSTART_GROUP = _KickstartFileFixture.KICKSTART_GROUP

    KICKSTART_PACKAGE = _KickstartFileFixture.KICKSTART_PACKAGE

    AVAILABLE_GROUPS = frozenset({KICKSTART_GROUP} if KICKSTART_GROUP else {})

    AVAILABLE_PACKAGES = frozenset({KICKSTART_PACKAGE} if KICKSTART_PACKAGE else {})

    def setUp(self):
        """Prepare the test fixture."""
        super(_KickstartCommandFixture, self).setUp()
        base = support.BaseCliStub(self.AVAILABLE_PACKAGES, self.AVAILABLE_GROUPS)
        cli = support.CliStub(base)
        self._command = kickstart.KickstartCommand(cli)
        cli.register_command(self._command)
        base.read_all_repos()
        base.basecmd = self._command.aliases[0]


class KickstartCommandTest(_KickstartCommandFixture, unittest.TestCase):
    """Unit tests of kickstart.KickstartCommand."""

    def setUp(self):
        """Prepare the test fixture."""
        super(KickstartCommandTest, self).setUp()
        self._log_handler = logging.StreamHandler(dnf.pycomp.StringIO())
        self._command.cli.logger.addHandler(self._log_handler)

    def tearDown(self):
        """Tear down the test fixture."""
        super(KickstartCommandTest, self).tearDown()
        self._command.cli.logger.removeHandler(self._log_handler)

    def test_run_group(self):
        """Test whether the group is installed."""
        support.command_run(self._command, [self._path])
        self.assertEqual(self._command.cli.base.installed_groups, {self.KICKSTART_GROUP})

    def test_run_morepaths(self):
        """Test whether it fails if multiple paths are given."""
        self.assertRaises(SystemExit, support.command_run, self._command, ['path1.ks', 'path2.ks'])

    def test_run_notfound(self):
        """Test whether it fails if the path does not exist."""
        self.assertRaises(dnf.exceptions.Error, support.command_run, self._command, ['non-existent.ks'])

    def test_run_package(self):
        """Test whether the package is installed."""
        support.command_run(self._command, [self._path])
        self.assertEqual(self._command.cli.base.installed_pkgs, {self.KICKSTART_PACKAGE})


class KickstartCommandNoCompAGroupTest(_KickstartCommandFixture, unittest.TestCase):
    """Unit tests of kickstart.KickstartCommand with no available group and a group in the file."""

    AVAILABLE_GROUPS = frozenset()

    def test_run(self):
        """Test whether it fails."""
        self.assertRaises(dnf.exceptions.Error, support.command_run, self._command, [self._path])


class KickstartCommandNoCompNoGroupTest(_KickstartCommandFixture, unittest.TestCase):
    """Unit tests of kickstart.KickstartCommand with no available group and no group in the file."""

    KICKSTART_GROUP = None

    AVAILABLE_GROUPS = frozenset()

    def test_run(self):
        """Test whether it does not fail."""
        try:
            support.command_run(self._command, [self._path])
        except dnf.exceptions.Error:
            self.fail()


class MaskableKickstartParserTest(unittest.TestCase):
    """Unit tests of kickstart.MaskableKickstartParser."""

    EXCLUDED_SECTION_OPENS = {pykickstart.sections.PackageSection.sectionOpen}

    ALL_SECTION_OPENS = ({pykickstart.sections.TracebackScriptSection.sectionOpen,
                          pykickstart.sections.PostScriptSection.sectionOpen,
                          pykickstart.sections.PreScriptSection.sectionOpen} |
                         EXCLUDED_SECTION_OPENS)

    def setUp(self):
        """Prepare the test fixture."""
        super(MaskableKickstartParserTest, self).setUp()
        handler = pykickstart.version.makeVersion()
        self._parser = kickstart.MaskableKickstartParser(handler)

    def test_mask_all(self):
        """Test mask_all."""
        original_sections = {
            section_open: self._parser.getSection(section_open)
            for section_open in self.ALL_SECTION_OPENS
        }
        for section in original_sections.values():
            self.assertNotIsInstance(section, pykickstart.sections.NullSection)

        self._parser.mask_all(self.EXCLUDED_SECTION_OPENS)

        for section_open in self.ALL_SECTION_OPENS:
            section = self._parser.getSection(section_open)
            if section_open in self.EXCLUDED_SECTION_OPENS:
                self.assertIs(section, original_sections[section_open])
            else:
                self.assertIsInstance(section, pykickstart.sections.NullSection)


class ParseKickstartPackagesTest(_KickstartFileFixture, unittest.TestCase):
    """Unit tests of kickstart.parse_kickstart_packages."""

    def test_group(self):
        """Test whether it parses groups."""
        packages = kickstart.parse_kickstart_packages(self._path)
        self.assertEqual(packages.groupList, [pykickstart.parser.Group(self.KICKSTART_GROUP)])

    def test_fail(self):
        """Test whether it fails if the path does not exist."""
        self.assertRaises(pykickstart.errors.KickstartError,
                          kickstart.parse_kickstart_packages, 'non-existent.ks')

    def test_package(self):
        """Test whether it parses packages."""
        packages = kickstart.parse_kickstart_packages(self._path)
        self.assertEqual(packages.packageList, [self.KICKSTART_PACKAGE])
