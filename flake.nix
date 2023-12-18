{
  description = "A very basic flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.11";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-utils.url = "github:numtide/flake-utils";
    epnix.url = "github:epics-extensions/EPNix";
    flake-compat.url = "https://flakehub.com/f/edolstra/flake-compat/1.tar.gz";
  };

  nixConfig.commit-lockfile-summary = "chore(deps): update flake.lock";

  outputs = {
    self,
    nixpkgs,
    poetry2nix,
    flake-utils,
    epnix,
    flake-compat,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [
          epnix.overlays.default
          (_final: _prev: {
            wetest = self.packages.${system}.default;
          })
        ];
      };
      inherit (epnix.packages.${system}) epics-base;
      inherit (poetry2nix.lib.mkPoetry2Nix {inherit pkgs;}) mkPoetryApplication;
    in {
      packages.default = let
        # Numpy 1.19.5 doesn't compile with Python3.10+
        #
        # This was fixed in later versions of Numpy, but Numpy >=1.20 doesn't
        # support Python 3.6, which we need to support older systems.
        python = pkgs.python39;
      in
        mkPoetryApplication {
          projectDir = ./.;

          inherit python;

          nativeBuildInputs = with pkgs; [makeWrapper];
          propagatedBuildInputs = with python.pkgs; [tkinter];

          postInstall = ''
            wrapProgram $out/bin/wetest \
              --set PYEPICS_LIBCA "${epics-base}/lib/linux-x86_64/libca.so"
          '';

          doCheck = true;
          checkPhase = ''
            runHook preCheck
            pytest
            runHook postCheck
          '';

          meta = {
            description = "Tests automation utility for EPICS";
            mainProgram = "wetest";
            license = epnix.lib.licenses.epics;
            maintainers = with epnix.lib.maintainers; [minijackson];
          };
        };

      devShells.default = pkgs.mkShell {
        inputsFrom = [self.packages.${system}.default];
        nativeBuildInputs = with pkgs; [poetry];
        env.PYEPICS_LIBCA = "${epics-base}/lib/linux-x86_64/libca.so";
      };

      checks = import ./nix/checks {inherit pkgs;};
    });
}
