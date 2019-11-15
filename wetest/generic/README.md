# How to use generic scripts ?

The way to use these scripts are using macros. Only in case of bug or missing features, srcipt modification are necessary.

You have to create your own script and call the generic script with the ```include``` feature. Thus you can give your parameters to the generic script. There are also ```sepecific``` model you can call.

As you can see, there are a lot of test in the generic sprits. Fore sure you don't need all of them for your applicationj. You just need to select the desired ones by using the ```IGNORE_...``` macros.. By default all the test are deslected (ignored).

## Unit test (developper tests)

The unit test goal is to test the range and limits of PVs. The tests are played in a random way so the channel has to be off before starting test because if it not the case, you may dammage the device supplied by your power supply. So there are 2 parts in the unit test:
 - init: which initialise the device (turn off the channel, reset, check fault)
 - test all range and limit PVs

 See ```specific/weTest_unit_CAENels_PS_FAST_1K5.yaml``` to get an example of use case..


## Functional test (operation tests: acceptance tests, interlock tests, ...)

Since there are many different power supply behavior, it was impossible to create a script for all the cases. So I split the test in 3 parts:
- init: which initialise the device (turn off the channel, reset, check fault)
- config: which configure the device (set voltage, current, polarity, interlocks,  regulation mode, ...)
- turn on: which turn on the channel (check permission, turn on, check status, check desired output)

See ```specific/weTest_functional_CAENels_PS_FAST_1K5_current.yaml``` to get an example of use case.

As you can see in the above script, it is sometimes necessary to call several times the ```config``` (or an other part) to fit the power supply behavior. Here you have to first power on the channel and then set the setpoint (current command).

## Specific models 

Files in ```specific``` folder can be seen as example but you can also use them if it is the power suplly you want to control.

The idea behind that, is if you known that it is a model very used, you can create a script to help WeTest community :).


## Contribute to the WeTest community :)

Don't hesitate to:
- report any bug in generic scripts
- ask for new features (ex: polarity and regulation mode (current or voltage) were the last features added)
- add more specific models scripts

Contact: Victor Nadot, victor.nadot@cea.fr