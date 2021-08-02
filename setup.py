from setuptools import setup
from Cython.Build import cythonize
import numpy
from distutils.extension import Extension

setup(
    name='bayesian_pdes',
    version='',
    packages=['bayesian_pdes'],
    url='',
    license='',
    author='benorn',
    author_email='',
    description='',
    requires=['numpy'],
    ext_modules=cythonize([
        Extension('*',
            ['bayesian_pdes/pairwise.pyx'],
            include_dirs=[numpy.get_include()]
        )
    ])
)
