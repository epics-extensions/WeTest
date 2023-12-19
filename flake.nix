{
  description = "A very basic flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.05";
    flake-utils.url = "github:numtide/flake-utils";
    epnix.url = "github:epics-extensions/EPNix";
    flake-compat.url = "https://flakehub.com/f/edolstra/flake-compat/1.tar.gz";
    nix-appimage = {
      url = "github:ralismark/nix-appimage";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    epnix,
    flake-compat,
    nix-appimage,
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
    in {
      packages.default = let
        # Numpy 1.19.5 doesn't compile with Python3.10+
        #
        # This was fixed in later versions of Numpy, but Numpy >=1.20 doesn't
        # support Python 3.6, which we need to support older systems.
        python = pkgs.python39;
      in
        pkgs.poetry2nix.mkPoetryApplication {
          projectDir = ./.;

          inherit python;

          nativeBuildInputs = with pkgs; [makeWrapper];
          propagatedBuildInputs = with python.pkgs; [tkinter];

          overrides = pkgs.poetry2nix.overrides.withDefaults (_final: prev: {
            reportlab = prev.reportlab.overridePythonAttrs (_old: {
              buildInputs = with pkgs; [(freetype.overrideAttrs (_: {dontDisableStatic = true;}))];
            });
          });

          postInstall = let
            inherit (epnix.packages.x86_64-linux) epics-base;
          in ''
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

      packages.AppImage = nix-appimage.bundlers.${system}.default self.packages.${system}.default;

      devShells.default = pkgs.mkShell {
        nativeBuildInputs = with pkgs; [poetry python39Full];
      };

      checks = import ./nix/checks {inherit pkgs;};
    });
}
