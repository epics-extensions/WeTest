{pkgs, ...}:
pkgs.nixosTest {
  name = "wetest-check-simple";

  nodes = {
    client = {
      environment.systemPackages = [pkgs.epnix.epics-base pkgs.wetest];
    };

    ioc = pkgs.epnixLib.testing.softIoc ''
      record(ai, "TEST_RANGE") { }
      record(ai, "TEST_VALUES") { }
      record(ai, "TEST_COMMANDS") { }
    '';
  };

  testScript = let
    scenario = pkgs.writeText "simple.yml" ''
      version: {major: 2, minor: 0, bugfix: 0}

      config:
        type: unit
        name: WeTest simple

      tests:
        - name: "range"
          delay: 0.2
          setter: "TEST_RANGE"
          getter: "TEST_RANGE"
          range: {start: 1, stop: 5}

        - name: "values"
          delay: 0.2
          setter: "TEST_VALUES"
          getter: "TEST_VALUES"
          values: [1, 2, 3, 4, 5]

        - name: "commands"
          commands:
            - name: "send 1"
              setter: "TEST_COMMANDS"
              set_value: 1
            - name: "get 1"
              getter: "TEST_COMMANDS"
              get_value: 1
            - name: "send 5"
              setter: "TEST_COMMANDS"
              set_value: 5
            - name: "get 5"
              getter: "TEST_COMMANDS"
              get_value: 5
    '';
  in ''
    start_all()

    ioc.wait_for_unit("ioc.service")

    ca = "EPICS_CA_AUTO_ADDR_LIST=no EPICS_CA_ADDR_LIST=ioc"

    client.wait_until_succeeds(f"{ca} caget TEST_RANGE")

    client.succeed(f"{ca} wetest --no-gui ${scenario} >&2")
    client.copy_from_vm("wetest-results.pdf")
  '';
}
