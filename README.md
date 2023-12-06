# WeTest

Tests automation utility for EPICS.

WeTest reads YAML files describing tests targeting EPICS PV,
run these tests in CLI with or without a GUI,
and generates a report in PDF.

## Installation

### Python and tkinter

WeTest is implemented in Python 3, which needs to be installed.

The `tkinter` module should be included in your python installation.
If not, you need to also install the corresponding package.
This module is needed for the graphical interface.

For example in Ubuntu:

```bash
sudo apt-get install python-tk
```

For example in CentOS:

```bash
sudo yum install tkinter
```

WeTest is currently successfully running on CentOS 7 and Ubuntu 18.04
(support for Windows is planned but not yet available).

### Build using Nix

First, install Nix.
Refer to the [Download Nix] page for instructions.

Then, run:

``` bash
nix-build
```

This builds WeTest and its dependencies,
and puts the compilation result under `./result`.

After running the build, you can run WeTest by running:

``` bash
./result/bin/wetest
```

If you want WeTest available in your global user environment,
then you can run:

``` bash
nix-env -i -f default.nix
```

  [Download Nix]: https://nixos.org/download#download-nix

### Build using Poetry

First, install Poetry.
Refer to the [Poetry documentation] for instructions.

To build the project,
you can run:

``` bash
poetry install
poetry build
```

Running WeTest can be done with:

``` bash
poetry run wetest [other arguments]
```

  [Poetry documentation]: https://python-poetry.org/docs/

### Set up pyepics

Setting up pyepics is *not* needed for the Nix build.

WeTest relies on the `pyepics` module,
and depending on your EPICS installation
you might need to set up the `PYEPICS_LIBCA` environment variable manually.

For instance:

``` bash
export PYEPICS_LIBCA=/opt/epics/bases/base-3.14.12.5/lib/centos7-x86_64/libca.so
```

You can find full explanation in the [pyepics installation] page.

  [pyepics installation]: http://cars9.uchicago.edu/software/python/pyepics3/installation.html#getting-started-setting-up-the-epics-environment

# Run WeTest

### Running tests

To run WeTest with a scenario file, use either:

``` bash
wetest <scenario.yaml>
wetest -s <scenario.yaml>
wetest --scenario <scenario.yaml>
```

You can provide several scenarios files in the CLI,
or you may use the `include` block within a scenario file.

### PV connection and naming

You can run WeTest without a scenario file
if you provide an EPICS DB directory or DB files.
In that case no test will run
and WeTest will monitor the PV connection status.

``` bash
wetest -d <epics_db_folder>
wetest --db <epics_db_folder> --naming ESS
```

By default WeTest will only the PVs found in the tests.
Using the `--db` option adds the new PVs to the PV list extracted from the tests.

The `--naming` or `-n` option checks the conformity of the PV name to the naming convention,
and sort the PVs by sections and subsections.

### change PDF report name

At the end of the test runs,
WeTest generates a PDF report in the current directory under the name `wetest-results.pdf`.
You can change this name using the `--pdf-output` option.

``` bash
wetest <scenario.yaml> -o <another_name.pdf>
wetest <scenario.yaml> --pdf-output  <another_location/another_name.pdf>
```

### Other options and documentation

More CLI options are available,
but aren't documented here.
Have a look in the `doc` directory.

Check the help option to have exhaustive list:

``` bash
wetest -h
```

## Writing scenarios files

Scenario files are YAML files.

As of today the only documentation about the content of scenario files are:

-   the PowerPoint presentation in the `doc` folder
-   the YAML schema validation file also in the `doc` folder

A user manual is planned but not yet available.

One may also find interesting example in the `test` directory.

Pre-made scenarios are also available in the `generic` folder.
These files are meant to be included in another scenario with macros
to activate and customize tests.

Here is another summary.

Content expected in a scenario file:

-   `version`: checks the compatibility of the file against the running version of WeTest
-   `config`: to define a scenario name,
    PV prefix,
    default values,
    and whether the tests should be shuffled (unit)
    or run in the order defined (functional)
-   `tests`: a list of test,
    see below for the expected content of a test
-   `macros`: macros can be defined here and will be substituted throughout the file
-   `include`: a list of scenario to run,
    macros can be provided to each included scenario,
    tests are run last by default,
    but this can be changed by adding test somewhere in the include list.
-   `name`: a name for the suite (report and GUI title),
    only the topmost file suitename will be used,
    included files suitename will be ignored.
    This parameter is also ignored when providing multiple files in the command line.

If a `tests` block is defined,
then a `config` block is expected too,
and conversely.

Content expected in a test:

-   `name`: test title,
    displayed CLI in GUI and report
-   `prefix`: string appended after the configuration prefix and before the PV name
-   `use_prefix`: whether to use append prefix from config
-   `delay`: wait time between setting and getting the PVs
-   `message`: free length description for the test,
    displayed in GUI and report
-   `setter`: name of the PV where to write a value
-   `getter`: name of the PV from where to read a value
-   `margin`: lets you to set a percentage tolerance when checking the value
-   `delta`: lets you to set a constant tolerance when checking the value
-   `finally`: put back to a known configuration
-   `ignore`: whether the test shouldn't be read
-   `skip`: whether the test shouldn't be run
-   `on_failure`: determines whether to continue,
    pause,
    or abort
    if the test fails
-   `retry`: number of time to try again the test if it failed

-   `range`: generate a list of values to test,
    available sub-fields are:
    -   `start`: starting value
    -   `stop`: end value
    -   `step`: space between values from start to stop
    -   `lin`: number of values linearly spaced between start and stop
    -   `geom`: number of values geometrically spaced between start and stop
    -   `include_start`: whether to test the start value
    -   `include_stop`: whether to test the stop value
    -   `sort`: whether the values should shuffled or ordered

-   `values`: custom list of value to test

-   `commands`: a list of highly customizable tests,
    available sub-fields are:
    -   `name`: command title,
        displayed CLI in GUI and report
    -   `message`: free length description for the command,
        displayed in GUI and report
    -   `margin`: lets to set a percentage tolerance when checking the value
    -   `delta`: lets to set a constant tolerance when checking the value
    -   `setter`: overrides the test setter PV name
    -   `getter`: overrides the test getter PV name
    -   `get_value`: value expected in the getter PV
    -   `set_value`: value to put in the setter PV
    -   `value`: same value for setter and getter PV
    -   `delay`: overrides the test delay
    -   `ignore`: ignore this command even if test isn't ignored
    -   `skip`: whether the command shouldn't be run
    -   `on_failure`: continue,
        pause,
        or abort,
        if the command fails

A test should have one of the three "test kind":
`range`,
`values`,
or `commands`.

## Development

This section is under works.

Pull requests, feature requests, and bug reports are welcome.

Aside from a proper user manual,
proper non-regression tests are today lacking,
so development might be a bit slow.
