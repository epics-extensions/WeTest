{
  description = "A very basic flake";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-22.11";

  outputs = { self, nixpkgs }: let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in {

    packages.x86_64-linux.default = pkgs.poetry2nix.mkPoetryApplication {
      projectDir = ./.;

      # Numpy 1.19.5 doesn't compile with Python3.10+
      #
      # This was fixed in later versions of Numpy, but Numpy >=1.20 doesn't
      # support Python 3.6, which we need to support older systems.
      python = pkgs.python39;

      propagatedBuildInputs = with pkgs.python39Packages; [ tkinter ];

      overrides = pkgs.poetry2nix.overrides.withDefaults (final: prev: {
        reportlab = prev.reportlab.overridePythonAttrs (old: {
          buildInputs = with pkgs; [ (freetype.overrideAttrs (_: { dontDisableStatic = true; })) ];
        });
      });
    };

    devShells.x86_64-linux.default = pkgs.mkShell {
      nativeBuildInputs = with pkgs; [ poetry python39Full ];
    };

  };
}
