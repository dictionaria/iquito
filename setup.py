from setuptools import setup


setup(
    name='cldfbench_iquito',
    py_modules=['cldfbench_iquito'],
    include_package_data=True,
    zip_safe=False,
    entry_points={
        'cldfbench.dataset': [
            'iquito=cldfbench_iquito:Dataset',
        ]
    },
    install_requires=[
        'cldfbench',
        'pydictionaria>=2.0',
    ],
    extras_require={
        'test': [
            'pytest-cldf',
        ],
    },
)
