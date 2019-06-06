from __future__ import print_function

import hashlib
import os
import re
import requests
import shutil
import subprocess
import sys

from distutils.command.build import build
from setuptools import setup, find_packages, Extension
from setuptools.command.build_ext import build_ext


OPENFST_VERSION = "1.7.2"


def copy(src, dst):
    print("copying {} -> {}".format(src, dst))
    shutil.copy(src, dst)


def get_file_sha256(filename):
    hasher = hashlib.md5()
    with open(filename, "rb") as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()


def get_filename_with_sha256(filename):
    sha256 = get_file_sha256(filename)
    basename = os.path.basename(filename)
    basename_parts = basename.split(".")
    libname, libext = basename_parts[0], ".".join(basename_parts[1:])
    return "%s-%s.%s" % (libname, sha256[:8], libext)


class OpenFstExtension(Extension):
    def __init__(self):
        Extension.__init__(self, name="openfst_python.pywrapfst", sources=[])


class OpenFstBuild(build):

    user_options = build.user_options + [
        ("download-dir=", None, "directory containing the openfst-%s.tar.gz file" % OPENFST_VERSION),
    ]

    @property
    def openfst_basename(self):
        return "openfst-%s.tar.gz" % OPENFST_VERSION

    def initialize_options(self):
        build.initialize_options(self)
        self.download_dir = None

    def finalize_options(self):
        build.finalize_options(self)
        #self.set_undefined_options("build_ext", ("download_dir", "download_dir"))
        if self.download_dir:
            openfst_tar_gz = os.path.join(self.download_dir, self.openfst_basename)
            assert os.path.isfile(openfst_tar_gz), 'File %s does not exist' % openfst_tar_gz
        else:
            self.download_dir = self.build_temp


class OpenFstBuildExt(build_ext):

    user_options = build_ext.user_options + [
        ("download-dir=", None, "directory containing the openfst-%s.tar.gz file" % OPENFST_VERSION),
    ]

    @property
    def openfst_basename(self):
        return "openfst-%s.tar.gz" % OPENFST_VERSION

    @property
    def openfst_dirname(self):
        return "%s/openfst-%s" % (self.build_temp, OPENFST_VERSION)

    @property
    def openfst_filename(self):
        return os.path.join(self.download_dir, self.openfst_basename)

    @property
    def openfst_url(self):
        base_url = "http://www.openfst.org/twiki/pub/FST/FstDownload"
        return "%s/%s" % (base_url, self.openfst_basename)

    @property
    def openfst_main_lib(self):
        return "%s/src/extensions/python/.libs/pywrapfst.so" % self.openfst_dirname

    @property
    def openfst_deps_libs(self):
        return [
            "%s/src/extensions/far/.libs/libfstfar.so.16" % self.openfst_dirname,
            "%s/src/extensions/far/.libs/libfstfarscript.so.16" % self.openfst_dirname,
            "%s/src/script/.libs/libfstscript.so.16" % self.openfst_dirname,
            "%s/src/lib/.libs/libfst.so.16" % self.openfst_dirname,
        ]

    @property
    def output_dir(self):
        return "%s/openfst_python" % self.build_lib


    def initialize_options(self):
        build_ext.initialize_options(self)
        self.download_dir = None

    def finalize_options(self):
        build_ext.finalize_options(self)
        self.set_undefined_options('build', ("download_dir", "download_dir"))

    def openfst_download(self):
        if os.path.exists(self.openfst_dirname):
            return

        if not os.path.isdir(self.build_temp):
            os.makedirs(self.build_temp)

        if not os.path.exists(self.openfst_filename):
            print("downloading from %s" % self.openfst_url)
            r = requests.get(self.openfst_url, verify=False, stream=True)
            r.raw.decode_content = True
            with open(self.openfst_filename, "wb") as f:
                shutil.copyfileobj(r.raw, f)

    def openfst_extract(self):
        if not os.path.exists(self.openfst_dirname):
            extract_cmd = ["tar", "xzf", self.openfst_filename, "-C", self.build_temp]
            subprocess.check_call(extract_cmd)

    def openfst_configure_and_make(self):
        if not os.path.exists(self.openfst_main_lib):
            copy("ac_python_devel.m4", "%s/m4" % self.openfst_dirname)
            old_dir = os.getcwd()
            os.chdir(self.openfst_dirname)
            if os.path.exists("Makefile"):
                subprocess.check_call(["make", "distclean"])
            subprocess.check_call(["aclocal"])
            subprocess.check_call(["autoconf", "-f"])
            configure_cmd = [
                "./configure",
                "--enable-compact-fsts",
                "--enable-compress",
                "--enable-const-fsts",
                "--enable-far",
                "--enable-linear-fsts",
                "--enable-lookahead-fsts",
                "--enable-python",
                "--enable-special",
            ]
            subprocess.check_call(configure_cmd)
            subprocess.check_call(["make", "-j4"])
            os.chdir(old_dir)

    def openfst_copy_libraries(self, ext):
        main_lib_output_path = os.path.join(self.build_lib, ext._file_name)
        copy(self.openfst_main_lib, main_lib_output_path)
        for src in self.openfst_deps_libs:
            dst = "%s/%s" % (self.output_dir, get_filename_with_sha256(src))
            copy(src, dst)

    def openfst_fix_libraries(self):
        def patchelf_needed(so_filename):
            patchelf_cmd = ("patchelf", "--print-needed", so_filename)
            output = subprocess.check_output(patchelf_cmd)
            if isinstance(output, bytes):
                return output.decode("utf-8").split()
            else:
                return output.split()

        def patchelf_replace(so_filename, oldso, newso):
            patchelf_cmd = ("patchelf", "--replace-needed", oldso, newso, so_filename)
            subprocess.check_call(patchelf_cmd)

        def patchelf_remove(so_filename, oldso):
            patchelf_cmd = ("patchelf", "--remove-needed", oldso, so_filename)
            subprocess.check_call(patchelf_cmd)

        def patchelf_rpath_origin(so_filename):
            patchelf_cmd = ("patchelf", "--set-rpath", "$ORIGIN", so_filename)
            subprocess.check_call(patchelf_cmd)

        def patchelf_replace_all(so_filename, so_map):
            for oldso in patchelf_needed(so_filename):
                if oldso in so_map:
                    newso = so_map[oldso]
                    patchelf_replace(so_filename, oldso, newso)

        def patchelf_remove_libpython(so_filename):
            for oldso in patchelf_needed(so_filename):
                if re.match(r"^libpython.*$", oldso) is not None:
                    patchelf_remove(so_filename, oldso)

        somap = {
            os.path.basename(dep): get_filename_with_sha256(dep)
            for dep in self.openfst_deps_libs
        }

        for sofile in os.listdir(self.output_dir):
            if re.match(r"^.*(\.so).*$", sofile) is not None:
                sofile = os.path.join(self.output_dir, sofile)
                patchelf_replace_all(sofile, somap)
                patchelf_remove_libpython(sofile)
                patchelf_rpath_origin(sofile)

    def run(self):
        self.openfst_download()
        self.openfst_extract()
        self.openfst_configure_and_make()
        self.openfst_copy_libraries(self.extensions[0])
        self.openfst_fix_libraries()

        cmd = self.get_finalized_command("build_py").build_lib
        self.write_stub(cmd, self.extensions[0])


with open(os.path.join(os.path.dirname(__file__), "README.md"), "r") as fh:
    long_description = fh.read()

setup(
    name="openfst_python",
    version=OPENFST_VERSION,
    description="Stand-alone OpenFST bindings for Python",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jpuigcerver/openfst-python",
    author="Joan Puigcerver",
    author_email="joapuipe@gmail.com",
    license="MIT",
    packages=find_packages(),
    ext_modules=[OpenFstExtension()],
    cmdclass=dict(build=OpenFstBuild, build_ext=OpenFstBuildExt),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    setup_requires=["requests"],
    zip_safe=False,
)
