package Glib::Install::Files;

$self = {
          'typemaps' => [
                          'typemap'
                        ],
          'libs' => '-lgobject-2.0 -lglib-2.0  -lgthread-2.0 -pthread -lglib-2.0 ',
          'deps' => [],
          'inc' => ' -I. -I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include  -pthread -I/usr/include/glib-2.0 -I/usr/lib/x86_64-linux-gnu/glib-2.0/include '
        };


@deps = @{ $self->{deps} };
@typemaps = @{ $self->{typemaps} };
$libs = $self->{libs};
$inc = $self->{inc};

	$CORE = undef;
	foreach (@INC) {
		if ( -f $_ . "/Glib/Install/Files.pm") {
			$CORE = $_ . "/Glib/Install/";
			last;
		}
	}

1;
